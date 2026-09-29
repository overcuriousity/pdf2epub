from pathlib import Path
import gc
import io
import json
import os
import sys

from PIL import Image


DEFAULT_CHUNK_PAGES = 10
DEFAULT_GPU_BATCH_SIZE = 1


def get_default_output_dir(input_path: Path) -> Path:
    """Return the default output directory for a PDF."""
    return input_path.parent / input_path.stem


def get_default_input_dir() -> Path:
    """Return (and create) the default input directory."""
    input_dir = Path.cwd() / "input"
    input_dir.mkdir(exist_ok=True)
    return input_dir


def save_images(images: dict, image_dir: Path) -> None:
    """Save images returned by Marker and close their PIL resources."""
    if not images:
        return
    image_dir.mkdir(parents=True, exist_ok=True)
    for filename, image_data in images.items():
        try:
            image_path = image_dir / filename
            image_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(image_data, Image.Image):
                image_data.save(image_path)
            elif isinstance(image_data, bytes):
                with Image.open(io.BytesIO(image_data)) as image:
                    image.save(image_path)
            elif isinstance(image_data, str) and Path(image_data).exists():
                with Image.open(image_data) as image:
                    image.save(image_path)
            else:
                print(f"Unsupported image data for {filename}: {type(image_data)}")
        except Exception as exc:
            print(f"Error saving image {filename}: {exc}")
        finally:
            if isinstance(image_data, Image.Image):
                image_data.close()


def _page_count(input_path: str) -> int:
    """Read a PDF's page count without rendering its pages."""
    from pypdfium2 import PdfDocument

    document = PdfDocument(input_path)
    try:
        return len(document)
    finally:
        document.close()


def _selected_pages(page_count: int, start_page: int | None, max_pages: int | None) -> list[int]:
    start = 0 if start_page is None else start_page
    if start < 0:
        raise ValueError("start_page must be zero or greater")
    if max_pages is not None and max_pages < 1:
        raise ValueError("max_pages must be greater than zero")
    if start >= page_count:
        raise ValueError(f"start_page {start} is outside this {page_count}-page PDF")
    stop = page_count if max_pages is None else min(page_count, start + max_pages)
    return list(range(start, stop))


def _chunks(items: list[int], size: int) -> list[list[int]]:
    if size <= 0:
        return [items]
    return [items[index:index + size] for index in range(0, len(items), size)]


def _low_memory_config(page_range: list[int]) -> dict:
    """Set Marker's own batch controls; Surya environment variables are insufficient."""
    batch_size = int(os.environ.get("PDF2EPUB_GPU_BATCH_SIZE", DEFAULT_GPU_BATCH_SIZE))
    if batch_size < 1:
        raise ValueError("PDF2EPUB_GPU_BATCH_SIZE must be greater than zero")
    return {
        "page_range": page_range,
        "layout_batch_size": batch_size,
        "detection_batch_size": batch_size,
        "ocr_error_batch_size": batch_size,
        "recognition_batch_size": batch_size,
        "table_rec_batch_size": batch_size,
        "equation_batch_size": batch_size,
    }


def _merge_metadata(all_metadata: list[dict]) -> dict:
    """Combine Marker metadata from page chunks into one document-level object."""
    if not all_metadata:
        return {}
    merged = dict(all_metadata[0])
    merged["page_stats"] = [
        stat for metadata in all_metadata for stat in metadata.get("page_stats", [])
    ]
    merged["table_of_contents"] = [
        entry
        for metadata in all_metadata
        for entry in metadata.get("table_of_contents", [])
    ]
    merged["processing_chunks"] = len(all_metadata)
    return merged


def _release_chunk(rendered) -> None:
    images = getattr(rendered, "images", {})
    for image in images.values():
        if isinstance(image, Image.Image):
            image.close()
    images.clear()
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


def convert_pdf(
    input_path: str,
    output_dir: Path,
    max_pages: int | None = None,
    start_page: int | None = None,
    chunk_pages: int = DEFAULT_CHUNK_PAGES,
) -> None:
    """Convert a PDF in bounded page chunks and transparently join the result."""
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict

        pages = _selected_pages(_page_count(input_path), start_page, max_pages)
        page_chunks = _chunks(pages, chunk_pages)
        output_dir.mkdir(parents=True, exist_ok=True)
        image_dir = output_dir / "images"
        per_chunk = chunk_pages if chunk_pages > 0 else len(pages)
        print(
            f"Processing {len(pages)} page(s) in {len(page_chunks)} chunk(s) "
            f"of up to {per_chunk} page(s)."
        )

        # Models are expensive but fixed-size. Reuse them while discarding each
        # chunk's rendered pages and tensors before starting the next chunk.
        models = create_model_dict()
        markdown_parts = []
        metadata_parts = []
        for chunk_number, page_range in enumerate(page_chunks, start=1):
            print(
                f"Converting chunk {chunk_number}/{len(page_chunks)} "
                f"(pages {page_range[0] + 1}-{page_range[-1] + 1})..."
            )
            converter = PdfConverter(
                config=_low_memory_config(page_range), artifact_dict=models
            )
            rendered = converter(input_path)
            markdown_parts.append(rendered.markdown.strip())
            metadata_parts.append(rendered.metadata)
            save_images(rendered.images, image_dir)
            del converter
            _release_chunk(rendered)
            del rendered

        stem = Path(input_path).stem
        md_output = output_dir / f"{stem}.md"
        md_output.write_text("\n\n".join(markdown_parts) + "\n", encoding="utf-8")
        print(f"Markdown saved to: {md_output}")
        meta_output = output_dir / f"{stem}_metadata.json"
        meta_output.write_text(
            json.dumps(_merge_metadata(metadata_parts), indent=2), encoding="utf-8"
        )
        print(f"Metadata saved to: {meta_output}")
        if image_dir.exists():
            print(f"Images saved to: {image_dir}")

        del models
        gc.collect()
    except Exception as exc:
        print(f"Error converting {input_path}: {exc}", file=sys.stderr)
        raise


def add_pdfs_to_queue(input_path: Path) -> list[Path]:
    """Return PDFs represented by an input file or directory."""
    if input_path.is_dir():
        pdfs = sorted(input_path.glob("*.pdf"))
        if not pdfs:
            print(f"No PDF files found in directory: {input_path}", file=sys.stderr)
            sys.exit(1)
        return pdfs
    if not input_path.is_file():
        print(f"Error: Input file does not exist: {input_path}", file=sys.stderr)
        sys.exit(1)
    if input_path.suffix.lower() != ".pdf":
        print(f"Error: Input file must be a PDF: {input_path}", file=sys.stderr)
        sys.exit(1)
    return [input_path]
