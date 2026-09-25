"""
Alternative OCR backend using Baidu's Unlimited-OCR vision-language model
(https://github.com/baidu/Unlimited-OCR).

Every page is rendered to an image and parsed by the model, so this backend is
aimed at scanned PDFs. It requires an NVIDIA GPU with CUDA; the model weights
(~6.7 GB, bfloat16) are downloaded from HuggingFace on first use.

This runs the model in-process through plain transformers. The vllm engine
(modules/vllm_ocr.py) sends the same pages to a vLLM server instead and reuses
the rendering and post-processing helpers defined here.
"""
from pathlib import Path
import json
import os
import re
import sys
import tempfile
import time

MODEL_NAME = "baidu/Unlimited-OCR"

# Rendering resolution for scanned pages. The model resizes internally
# (base_size=1024 with 640px crops), so higher DPI mostly helps image crops.
RENDER_DPI = 200

# One detected block: "<|det|>category [x1, y1, x2, y2]<|/det|>content".
# Coordinates are normalised to 0-999 relative to the page image.
DET_RE = re.compile(
    r"<\|det\|>\s*([A-Za-z_][\w-]*)\s*(\[[^\]]*\])?\s*<\|/det\|>(.*)", re.DOTALL
)
REF_RE = re.compile(r"<\|/?ref\|>")
BBOX_RE = re.compile(r"-?\d+(?:\.\d+)?")

_model = None
_tokenizer = None


def _load_model():
    """Load the model once and reuse it for every PDF in the queue."""
    global _model, _tokenizer
    if _model is not None:
        return _model, _tokenizer

    # Peak VRAM sits just under 8 GB; without this, fragmentation alone makes
    # an 8 GB card run out of memory on Linux. Must be set before CUDA starts.
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    import torch
    from transformers import AutoModel, AutoTokenizer

    if not torch.cuda.is_available():
        raise RuntimeError(
            "Unlimited-OCR requires an NVIDIA GPU with CUDA; "
            "use the default marker engine on CPU."
        )

    print(f"Loading {MODEL_NAME} (downloaded on first run)...")
    _tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    _model = AutoModel.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
        use_safetensors=True,
        dtype=torch.bfloat16,
    )
    _model = _model.eval().cuda()
    return _model, _tokenizer


def page_indices(page_count: int, max_pages: int = None, start_page: int = None) -> list[int]:
    start = start_page or 0
    end = page_count if max_pages is None else min(page_count, start + max_pages)
    return list(range(start, end))


def render_page(pdf, idx: int):
    """Render page idx of an open pypdfium2 document to a PIL image."""
    page = pdf[idx]
    image = page.render(scale=RENDER_DPI / 72).to_pil()
    page.close()
    return image


def write_output(
    output_dir: Path,
    stem: str,
    page_texts: list[str],
    pages: list[int],
    elapsed: float,
    engine: str,
    **extra,
) -> None:
    """Write <stem>.md and <stem>_metadata.json the way mark2epub expects."""
    md_output = output_dir / f"{stem}.md"
    md_output.write_text("\n\n".join(t for t in page_texts if t), encoding="utf-8")
    print(f"Markdown saved to: {md_output}")

    metadata = {
        "ocr_engine": engine,
        "pages": [i + 1 for i in pages],
        "seconds_total": round(elapsed, 1),
        "seconds_per_page": round(elapsed / max(len(pages), 1), 2),
        **extra,
    }
    meta_output = output_dir / f"{stem}_metadata.json"
    with open(meta_output, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to: {meta_output}")
    print(f"OCR finished: {len(pages)} pages in {elapsed:.1f}s")


def _parse_bbox(raw: str, width: int, height: int):
    nums = [float(n) for n in BBOX_RE.findall(raw or "")]
    if len(nums) < 4:
        return None
    x1, y1, x2, y2 = nums[:4]
    box = (
        int(x1 / 999 * width),
        int(y1 / 999 * height),
        int(x2 / 999 * width),
        int(y2 / 999 * height),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def page_output_to_markdown(raw: str, page_image, image_dir: Path, page_no: int) -> str:
    """
    Turn the model's tagged output for one page into plain markdown.

    Detection tags are stripped; blocks labelled "image" are cropped from the
    page render, saved to image_dir and referenced as images/<name>.jpg.
    """
    raw = raw.replace("<｜end▁of▁sentence｜>", "")
    width, height = page_image.size
    blocks = []
    cur = None
    img_idx = 0

    for line in raw.splitlines():
        line = REF_RE.sub("", line).rstrip()
        if not line:
            continue
        m = DET_RE.match(line)
        if m:
            category, bbox, content = m.group(1), m.group(2), m.group(3).strip()
            if cur is not None:
                blocks.append(cur)
            cur = None
            if category == "image":
                box = _parse_bbox(bbox, width, height)
                if box:
                    image_dir.mkdir(parents=True, exist_ok=True)
                    name = f"page{page_no:04d}_img{img_idx}.jpg"
                    page_image.crop(box).convert("RGB").save(image_dir / name, quality=90)
                    blocks.append([f"![](images/{name})"])
                    img_idx += 1
                continue
            cur = [content] if content else []
            continue
        if cur is None:
            cur = []
        cur.append(line)
    if cur is not None:
        blocks.append(cur)

    text = "\n\n".join("\n".join(b) for b in blocks if b)
    return text.replace("\\coloneqq", ":=").replace("\\eqqcolon", "=:").strip()


def convert_pdf(
    input_path: str,
    output_dir: Path,
    max_pages: int = None,
    start_page: int = None,
) -> None:
    """Convert a PDF to markdown page by page with Unlimited-OCR."""
    import pypdfium2 as pdfium

    try:
        model, tokenizer = _load_model()

        output_dir.mkdir(parents=True, exist_ok=True)
        image_dir = output_dir / "images"
        stem = Path(input_path).stem

        pdf = pdfium.PdfDocument(input_path)
        pages = page_indices(len(pdf), max_pages, start_page)
        page_texts = []
        started = time.time()

        with tempfile.TemporaryDirectory(prefix="unlimited_ocr_") as tmp:
            tmp_dir = Path(tmp)
            for n, idx in enumerate(pages, 1):
                page_started = time.time()
                page_image = render_page(pdf, idx)
                page_path = tmp_dir / f"page_{idx + 1:04d}.png"
                page_image.save(page_path)

                # eval_mode=True returns the raw text instead of streaming it
                # to stdout and writing result.md into output_path.
                raw = model.infer(
                    tokenizer,
                    prompt="<image>document parsing.",
                    image_file=str(page_path),
                    output_path=str(tmp_dir / "infer"),
                    base_size=1024,
                    image_size=640,
                    crop_mode=True,
                    max_length=32768,
                    no_repeat_ngram_size=35,
                    ngram_window=128,
                    eval_mode=True,
                )
                page_texts.append(
                    page_output_to_markdown(raw or "", page_image, image_dir, idx + 1)
                )
                page_image.close()
                print(
                    f"  page {idx + 1} ({n}/{len(pages)}) "
                    f"in {time.time() - page_started:.1f}s"
                )

        pdf.close()
        write_output(
            output_dir, stem, page_texts, pages, time.time() - started, MODEL_NAME
        )

    except Exception as e:
        print(f"Error converting {input_path}: {str(e)}", file=sys.stderr)
        raise
