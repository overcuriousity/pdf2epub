import argparse
from pathlib import Path
import sys
import json
import marker 
from PIL import Image
import io

def get_default_output_dir(input_path: Path) -> Path:
    """
    Generate default output directory path based on input PDF path.
    Creates a directory with same name as PDF (without extension) next to the PDF.
    """
    return input_path.parent / input_path.stem

def get_default_input_dir() -> Path:
    """
    Get default input directory (./input) relative to current working directory.
    Creates it if it doesn't exist.
    """
    input_dir = Path.cwd() / 'input'
    input_dir.mkdir(exist_ok=True)
    return input_dir


def save_images(images: dict, image_dir: Path) -> None:
    """
    Save images with proper error handling and format detection.
    Preserves original image filenames from the input.
    
    Args:
        images: Dictionary of images from marker-pdf conversion where keys are filenames
        image_dir: Directory to save images to
    """
    if not images:
        print("No images found in document")
        return
        
    image_dir.mkdir(exist_ok=True)
    saved_count = 0
    
    for filename, image_data in images.items():
        try:
            # Skip if image data is None or empty
            if not image_data:
                continue
                
            image_path = image_dir / filename
            
            # Handle different image data formats
            if isinstance(image_data, Image.Image):
                image_data.save(image_path)
                saved_count += 1
                    
            elif isinstance(image_data, bytes):
                img = Image.open(io.BytesIO(image_data))
                img.save(image_path)
                saved_count += 1
                    
            elif isinstance(image_data, str):
                if Path(image_data).exists():
                    img = Image.open(image_data)
                    img.save(image_path)
                    saved_count += 1
                else:
                    print(f"Image path does not exist: {image_data}")
            else:
                print(f"Unsupported image data type for {filename}: {type(image_data)}")
                
        except Exception as e:
            print(f"Error saving image {filename}: {str(e)}")
            continue
            
    if saved_count > 0:
        print(f"Successfully saved {saved_count} images to: {image_dir}")
    else:
        print("No valid images were found to save")

def convert_pdf(
    input_path: str,
    output_dir: Path,
    max_pages: int = None,
    start_page: int = None,
) -> None:
    """
    Convert a single PDF file to markdown format with enhanced image handling.
    """
    try:
        from marker.models import create_model_dict
        from marker.converters.pdf import PdfConverter

        models = create_model_dict()

        # Build page_range config. marker-pdf 1.x requires an explicit list of
        # page indices; there is no "start to end" shorthand. If start_page is
        # given without max_pages we cannot construct the range without knowing
        # the document's page count, so we warn and process all pages instead.
        config = {}
        if max_pages is not None:
            s = start_page or 0
            config["page_range"] = list(range(s, s + max_pages))
        elif start_page is not None:
            print(
                f"Warning: --start-page requires --max-pages in marker-pdf 1.x "
                f"(no open-ended page range is supported). Processing all pages."
            )

        converter = PdfConverter(config=config, artifact_dict=models)
        rendered = converter(input_path)

        full_text = rendered.markdown
        images = rendered.images
        metadata = rendered.metadata

        # All output will go to the output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save markdown content
        md_output = output_dir / f"{Path(input_path).stem}.md"
        md_output.write_text(full_text, encoding='utf-8')
        print(f"Markdown saved to: {md_output}")

        # Save metadata as JSON
        meta_output = output_dir / f"{Path(input_path).stem}_metadata.json"
        with open(meta_output, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        print(f"Metadata saved to: {meta_output}")

        # Enhanced image handling
        try:
            if images:
                image_dir = output_dir / "images"
                save_images(images, image_dir)

                # Cleanup PIL Images
                for img in images.values():
                    if isinstance(img, Image.Image):
                        try:
                            img.close()
                        except Exception as e:
                            print(f"Warning: Failed to close image: {e}")
                images.clear()
        except Exception as e:
            print(f"Warning: Error during image cleanup: {e}")

    except Exception as e:
        print(f"Error converting {input_path}: {str(e)}", file=sys.stderr)
        sys.exit(1)

    
def add_pdfs_to_queue(input_path: Path) -> list[Path]:
    """
    Add PDF files to the processing queue.
    If input_path is a directory, add all PDFs in it.
    If input_path is a file, add just that file.
    """
    queue = []
    
    if input_path.is_dir():
        pdfs = list(input_path.glob('*.pdf'))
        if not pdfs:
            print(f"No PDF files found in directory: {input_path}", file=sys.stderr)
            sys.exit(1)
        queue.extend(pdfs)
    else:
        if not input_path.is_file():
            print(f"Error: Input file does not exist: {input_path}", file=sys.stderr)
            sys.exit(1)
        if input_path.suffix.lower() != '.pdf':
            print(f"Error: Input file must be a PDF: {input_path}", file=sys.stderr)
            sys.exit(1)
        queue.append(input_path)
        
    return queue
