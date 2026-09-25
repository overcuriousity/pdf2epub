# Handover: Unlimited-OCR on Fedora with vLLM

Written 2026-09-25 when the work moved from Windows to a Fedora machine.
Claude Code on Fedora should read this whole file first, then do the tasks in
order. Ask the user before anything that needs `sudo`, a reboot, a push, or a
merge into `main`.

## Status (2026-09-25, Fedora)

All tasks below are done on branch `unlimited-ocr-backend` (not pushed).
`--ocr-engine vllm` works on the RTX 4060 at ~1.05–1.3 s per page, versus
~4–6 s for marker and ~14 s for the transformers engine. The README has the
working Podman command and the measured numbers. What differed from the plan:

- The recipe's bf16 settings do not fit 8 GB next to the desktop. The server
  needs `--quantization fp8 --skip-mm-profiling` (see README for why), and
  rootless Podman needs `--security-opt label=disable` for SELinux.
- FP8 misreads roughly 1 word in 2,000; the bf16 transformers engine did not.
- The transformers engine needs `torchvision` and, on Linux,
  `expandable_segments` (now set inside the module) to avoid running out of
  memory. It is ~4x faster here than it was on Windows.
- Only a synthetic scan was tested. Re-check quality on a real scanned book.

## Why this exists

The user converts **scanned** books with this project. The slow step is
marker's "Recognizing Text" (Surya OCR). They want to try Baidu's
[Unlimited-OCR](https://github.com/baidu/Unlimited-OCR) because it is said to
be faster.

On Windows it was not faster. Baidu's speed claims come from serving the model
with **vLLM** (or SGLang), which only runs on Linux. The goal on Fedora is to
serve the model with vLLM and see whether that beats marker.

## Current state (branch `unlimited-ocr-backend`)

- `main.py` has `--ocr-engine marker|unlimited`. The default is `marker`, and
  it is unchanged.
- `modules/unlimited_ocr.py` runs the model in-process through
  `transformers` with `trust_remote_code=True`:
  - it renders each page with `pypdfium2`, which marker already installs, at
    200 DPI
  - it calls `model.infer(..., eval_mode=True)` once per page, which returns
    the raw text
  - `page_output_to_markdown()` removes the `<|det|>category [x1,y1,x2,y2]<|/det|>`
    tags. Coordinates are normalised to 0–999. It crops `image` blocks into
    `images/pageNNNN_imgK.jpg` and writes a markdown image link for each.
  - it writes `<stem>.md` and `<stem>_metadata.json` with the timings, laid
    out so the existing EPUB step (`modules/mark2epub.py`) works unchanged
- `README.md` documents the engine.

### Measured on Windows (RTX 4060, 8 GB VRAM)

These numbers come from a synthetic 3-page scanned PDF with Indonesian text.

| Engine | Time per page | Notes |
|---|---|---|
| marker (Surya) | ~15 s | 44 s total for 3 pages, including model load |
| Unlimited-OCR via transformers | ~62 s | ~13 tokens/s, peak 7.05 GiB VRAM, ~1,400 output tokens for a dense page |

The OCR output was good. It read the text correctly, found the heading and the
page number, and did not loop. The speed was the only problem.

## Tasks

### 1. Check the machine

```bash
cat /etc/fedora-release; uname -r
nvidia-smi                      # driver present? GPU model and VRAM?
python3 --version; which uv podman docker
```

If `nvidia-smi` is missing, the NVIDIA driver is not installed. On Fedora it
comes from RPM Fusion (`akmod-nvidia`, `xorg-x11-drv-nvidia-cuda`). It needs
`sudo`, a kernel module build and a reboot. Give the user the commands and
wait for them to run them. Do not run them yourself.

### 2. Python environment for this repo

`requirements.txt` recommends Python 3.13. marker-pdf pins `Pillow<11`, and
there are no Pillow wheels for 3.14. Recent Fedora releases default to 3.14,
so use `uv` to get 3.13:

```bash
uv venv --python 3.13 .venv && source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install addict easydict matplotlib     # needed by the model's remote code
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

If CUDA shows `False`, reinstall torch from the CUDA index that matches the
driver (see pytorch.org). Keep the torch version compatible with marker-pdf.

### 3. Baseline tests (before vLLM)

Ask the user for a real scanned PDF. If there is none, make a synthetic one:
render a few A4 pages of text and a picture with Pillow at 200 DPI, add a
slight rotation and noise, and save them as an image-only PDF.

Always pass `--skip-epub`. The EPUB step asks for metadata interactively and
fails with `EOFError` when there is no terminal.

```bash
time python main.py scan.pdf out_marker --skip-epub --max-pages 3
time python main.py scan.pdf out_unlimited --skip-epub --max-pages 3 --ocr-engine unlimited
ruff check --select E9,F .     # this is the only check CI runs; there is no test suite
```

Record the time per page for each engine. The unlimited engine prints a line
per page and saves the timings in `<stem>_metadata.json`.

### 4. Serve Unlimited-OCR with vLLM

The architecture is not in the stable vLLM wheel. Use the dedicated image
`vllm/vllm-openai:unlimited-ocr`. The official recipe is at
https://recipes.vllm.ai/baidu/Unlimited-OCR, and it uses Docker:

```bash
docker run --rm --gpus all --network host --ipc host \
  vllm/vllm-openai:unlimited-ocr \
  baidu/Unlimited-OCR \
  --trust-remote-code \
  --logits_processors vllm.model_executor.models.unlimited_ocr:NGramPerReqLogitsProcessor \
  --no-enable-prefix-caching \
  --mm-processor-cache-gb 0
```

Fedora ships Podman rather than Docker. For GPU access, install
`nvidia-container-toolkit` (needs sudo; ask the user) and generate the CDI
spec with `sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`. Then
run:

```bash
podman run --rm --device nvidia.com/gpu=all --network host --ipc host \
  -v ~/.cache/huggingface:/root/.cache/huggingface:Z \
  docker.io/vllm/vllm-openai:unlimited-ocr \
  baidu/Unlimited-OCR \
  --trust-remote-code \
  --logits_processors vllm.model_executor.models.unlimited_ocr:NGramPerReqLogitsProcessor \
  --no-enable-prefix-caching \
  --mm-processor-cache-gb 0 \
  --gpu-memory-utilization 0.90 --max-model-len 8192
```

- The volume mount caches the ~6.7 GB of weights between runs. `:Z` is needed
  because of SELinux.
- The recipe says 8 GB of VRAM is the minimum. If the GPU is that small,
  `--max-model-len 8192` and `--gpu-memory-utilization` keep the KV cache from
  running out of memory. Adjust them if it still fails. One dense page is
  about 1,400 output tokens.
- vLLM reserves most of the GPU. Stop the server before running marker or the
  transformers engine.
- The server listens on `http://localhost:8000/v1`. Check it with
  `curl localhost:8000/v1/models`.

Quick check with a single page. The request must follow the recipe exactly,
otherwise the output comes back empty or loops:

```python
from openai import OpenAI
client = OpenAI(api_key="EMPTY", base_url="http://localhost:8000/v1", timeout=3600)
r = client.chat.completions.create(
    model="baidu/Unlimited-OCR",
    messages=[{"role": "user", "content": [
        {"type": "text", "text": "<image>document parsing."},   # must start with <image>
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,<...>"}},
    ]}],
    max_tokens=8192, temperature=0.0,
    extra_body={"skip_special_tokens": False,                 # keep the <|det|> tags
                "vllm_xargs": {"ngram_size": 35, "window_size": 128}},
)
```

### 5. Add a `vllm` engine to the program

Add `--ocr-engine vllm` and `--vllm-url` (default `http://localhost:8000/v1`).

- Put the client in a new module or next to the existing code. Share the page
  rendering and `page_output_to_markdown()` with the transformers engine
  instead of copying them.
- The vllm engine must not import or load the model locally.
- Send one request per page, with a few pages in flight at once (for example
  `ThreadPoolExecutor`, about 4 to 8 workers). vLLM batches concurrent
  requests, and most of the speedup comes from that. Keep the pages in order
  in the output.
- Encode each page as a base64 PNG data URL, rendered at 200 DPI.
- Use the request parameters from section 4. For a single page, use
  `window_size=128`.
- Use `requests` (already installed through transformers/marker) or add
  `openai` to requirements. Whichever you pick, list it in the README.
- If the server is not running, fail with a clear message that shows the
  `podman run` command.
- Put the same `<stem>.md`, `images/` and `_metadata.json` output next to the
  PDF, with timings. Leave `mark2epub.py` alone.

### 6. Benchmark and report

Run marker, the transformers engine and the vllm engine on the same pages.
Report a table with seconds per page, total time and VRAM, plus a short
judgement of quality (compare the `.md` files). Update README with the vllm
engine, the Podman command and the measured numbers. Commit on this branch.
Do not push or merge unless the user asks.

## Gotchas already found

- `Some weights ... newly initialized: ['model.vision_model.embeddings.position_ids']`
  is harmless. It is a buffer, not a trained weight.
- The "attention mask is not set" warnings come from Baidu's remote code.
  Ignore them.
- In the transformers engine, `max_length=32768` can make a slow page look
  like it hangs, because no output is streamed in `eval_mode`. To see
  tokens/s, call `model.infer(..., tps_interval=5)` without `eval_mode`, and
  use a smaller `max_length`.
- marker 1.x needs `--max-pages` whenever `--start-page` is used.
- The `docs/marker/marker_README.md` in this repo describes an older marker.
  Its `OCR_ENGINE=ocrmypdf` option does not apply to marker 1.10.
