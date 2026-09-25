"""
OCR backend that sends pages to Baidu's Unlimited-OCR served by vLLM.

The model is not loaded here; it runs in a separate vLLM server (Linux +
NVIDIA GPU, see README), which start_server() launches in Podman when none is
running. Each page is rendered to a PNG and posted to the
server's OpenAI-compatible chat endpoint. Several pages are kept in flight so
vLLM can batch them, which is where the speedup over the transformers engine
comes from. Rendering and post-processing are shared with modules/unlimited_ocr.
"""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
import base64
import io
import shutil
import subprocess
import sys
import time

import requests

from modules.unlimited_ocr import (
    MODEL_NAME,
    page_indices,
    page_output_to_markdown,
    render_page,
    write_output,
)

DEFAULT_URL = "http://localhost:8000/v1"
DEFAULT_WORKERS = 8

CONTAINER_NAME = "pdf2epub-vllm"
IMAGE = "docker.io/vllm/vllm-openai:unlimited-ocr"
STARTUP_TIMEOUT = 20 * 60  # the first start pulls the image and the weights

# Settings that fit an 8 GB card that also drives the desktop; see README for
# what each memory flag is for and what to drop on a bigger GPU.
PODMAN_ARGS = [
    "--device", "nvidia.com/gpu=all",
    "--security-opt", "label=disable",
    "--network", "host",
    "--ipc", "host",
    "-e", "PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True",
]
VLLM_ARGS = [
    "--trust-remote-code",
    "--logits_processors",
    "vllm.model_executor.models.unlimited_ocr:NGramPerReqLogitsProcessor",
    "--no-enable-prefix-caching",
    "--mm-processor-cache-gb", "0",
    "--quantization", "fp8",
    "--gpu-memory-utilization", "0.85",
    "--max-model-len", "8192",
    "--skip-mm-profiling",
]

SERVER_COMMAND = """\
podman run --rm --device nvidia.com/gpu=all --security-opt label=disable \\
  --network host --ipc host \\
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \\
  -v ~/.cache/huggingface:/root/.cache/huggingface \\
  -v ~/.cache/vllm:/root/.cache/vllm \\
  docker.io/vllm/vllm-openai:unlimited-ocr \\
  baidu/Unlimited-OCR \\
  --trust-remote-code \\
  --logits_processors vllm.model_executor.models.unlimited_ocr:NGramPerReqLogitsProcessor \\
  --no-enable-prefix-caching \\
  --mm-processor-cache-gb 0 \\
  --quantization fp8 --gpu-memory-utilization 0.85 \\
  --max-model-len 8192 --skip-mm-profiling"""


def _served_models(base_url: str):
    """Return the model ids served at base_url, or None if nothing answers."""
    try:
        r = requests.get(f"{base_url}/models", timeout=5)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]
    except requests.RequestException:
        return None


def _podman(*args, check=False):
    return subprocess.run(["podman", *args], capture_output=True, text=True, check=check)


def start_server(base_url: str = DEFAULT_URL) -> bool:
    """
    Make sure a vLLM server answers at base_url, starting one in Podman if not.

    Returns True when this call started the container, so the caller knows to
    stop it again with stop_server(). Only local URLs are started.
    """
    base_url = base_url.rstrip("/")
    if _served_models(base_url) is not None:
        return False

    url = urlparse(base_url)
    if url.hostname not in ("localhost", "127.0.0.1", "::1") or not shutil.which("podman"):
        raise RuntimeError(
            f"No vLLM server reachable at {base_url}, and it cannot be started "
            f"automatically (needs a local URL and podman). Start one first, "
            f"for example:\n\n{SERVER_COMMAND}\n"
        )

    mounts = []
    for name in ("huggingface", "vllm"):
        cache = Path.home() / ".cache" / name
        cache.mkdir(parents=True, exist_ok=True)
        mounts += ["-v", f"{cache}:/root/.cache/{name}"]

    _podman("rm", "-f", CONTAINER_NAME)
    cmd = [
        "run", "-d", "--name", CONTAINER_NAME, *PODMAN_ARGS, *mounts,
        IMAGE, MODEL_NAME, *VLLM_ARGS, "--port", str(url.port or 8000),
    ]
    result = _podman(*cmd)
    if result.returncode != 0:
        raise RuntimeError(f"podman could not start the vLLM server:\n{result.stderr.strip()}")

    print(
        f"Starting vLLM server in podman container {CONTAINER_NAME} "
        "(about 2 minutes; the first run also downloads the image and model)..."
    )
    started = time.time()
    try:
        while time.time() - started < STARTUP_TIMEOUT:
            if _served_models(base_url) is not None:
                print(f"vLLM server ready after {time.time() - started:.0f}s")
                return True
            state = _podman("inspect", "-f", "{{.State.Running}}", CONTAINER_NAME)
            if state.stdout.strip() != "true":
                logs = _podman("logs", "--tail", "15", CONTAINER_NAME)
                raise RuntimeError(
                    "vLLM server exited during startup. Last log lines:\n"
                    + (logs.stdout + logs.stderr).strip()
                )
            time.sleep(2)
        raise RuntimeError(f"vLLM server not ready after {STARTUP_TIMEOUT // 60} minutes")
    except BaseException:
        stop_server()
        raise


def stop_server() -> None:
    """Stop and remove the container started by start_server()."""
    print(f"Stopping vLLM server ({CONTAINER_NAME})...")
    _podman("stop", "-t", "10", CONTAINER_NAME)
    _podman("rm", "-f", CONTAINER_NAME)


def _check_server(base_url: str) -> str:
    """Return the served model name, or fail with instructions to start vLLM."""
    models = _served_models(base_url)
    if models is None:
        raise RuntimeError(
            f"No vLLM server reachable at {base_url}. Start one first, "
            f"for example:\n\n{SERVER_COMMAND}\n"
        )
    if MODEL_NAME in models:
        return MODEL_NAME
    if len(models) == 1:
        return models[0]
    raise RuntimeError(f"{MODEL_NAME} is not served at {base_url}; found {models}")


def pad_to_tile_grid(image):
    """
    Pad a page with white to exactly 2:3 (or 3:2 for landscape pages).

    vLLM tiles each image into 640 px crops on the grid (up to 32 crops) whose
    aspect ratio is closest to the image's, so a book page only slightly wider
    than 2:3 becomes a 3x4 or 4x5 grid of upscaled crops. Encoding those needs
    700 MB and more at once, which runs an 8 GB card out of memory. At exactly
    2:3 the page always gets 6 crops, like an A4 page. Detection boxes are
    relative to the padded image, so image blocks are cropped from it.
    """
    from PIL import Image

    w, h = image.size
    tw, th = (2, 3) if w <= h else (3, 2)
    new_w, new_h = max(w, -(-h * tw // th)), max(h, -(-w * th // tw))
    if (new_w, new_h) == (w, h):
        return image
    padded = Image.new(image.mode, (new_w, new_h), "white")
    padded.paste(image, ((new_w - w) // 2, (new_h - h) // 2))
    image.close()
    return padded


def _ocr_page(base_url: str, model: str, image) -> tuple[str, str, float]:
    """Send one page image and return (raw output, finish reason, seconds)."""
    started = time.time()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    # Follows the vLLM recipe exactly; other prompts or dropping the special
    # tokens give empty or looping output. max_tokens is left to the server,
    # which caps it at whatever --max-model-len leaves after the image tokens.
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "<image>document parsing."},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]}],
        "temperature": 0.0,
        "skip_special_tokens": False,
        "vllm_xargs": {"ngram_size": 35, "window_size": 128},
    }
    r = requests.post(f"{base_url}/chat/completions", json=payload, timeout=3600)
    if not r.ok:
        raise RuntimeError(f"vLLM returned {r.status_code}: {r.text[:500]}")
    choice = r.json()["choices"][0]
    return choice["message"]["content"] or "", choice.get("finish_reason"), time.time() - started


def convert_pdf(
    input_path: str,
    output_dir: Path,
    max_pages: int = None,
    start_page: int = None,
    base_url: str = DEFAULT_URL,
    workers: int = DEFAULT_WORKERS,
) -> None:
    """Convert a PDF to markdown page by page through a vLLM server."""
    import pypdfium2 as pdfium

    base_url = base_url.rstrip("/")
    try:
        model = _check_server(base_url)

        output_dir.mkdir(parents=True, exist_ok=True)
        image_dir = output_dir / "images"
        stem = Path(input_path).stem

        pdf = pdfium.PdfDocument(input_path)
        pages = page_indices(len(pdf), max_pages, start_page)
        page_texts = []
        page_seconds = []
        started = time.time()

        # Pages are rendered here (pdfium is not thread-safe) and at most
        # 2 * workers are held in memory, so long books do not pile up images.
        pending = deque()

        def finish_oldest():
            idx, image, future = pending.popleft()
            raw, reason, seconds = future.result()
            if reason == "length":
                print(f"  warning: page {idx + 1} hit the token limit and is truncated")
            page_texts.append(page_output_to_markdown(raw, image, image_dir, idx + 1))
            page_seconds.append(round(seconds, 1))
            image.close()
            print(
                f"  page {idx + 1} ({len(page_texts)}/{len(pages)}) "
                f"request {seconds:.1f}s, elapsed {time.time() - started:.1f}s"
            )

        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for idx in pages:
                    image = pad_to_tile_grid(render_page(pdf, idx))
                    pending.append((idx, image, pool.submit(_ocr_page, base_url, model, image)))
                    while len(pending) >= 2 * workers or pending and pending[0][2].done():
                        finish_oldest()
                while pending:
                    finish_oldest()
        finally:
            # Closing here rather than at interpreter exit avoids pdfium's
            # "library is destroyed" warning when a request fails.
            pdf.close()

        write_output(
            output_dir,
            stem,
            page_texts,
            pages,
            time.time() - started,
            f"{MODEL_NAME} (vLLM)",
            vllm_url=base_url,
            workers=workers,
            request_seconds=page_seconds,
        )

    except Exception as e:
        print(f"Error converting {input_path}: {str(e)}", file=sys.stderr)
        raise
