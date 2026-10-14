#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
import modules.pdf2md as pdf2md
import modules.mark2epub as mark2epub
import modules.metadata as metadata_lib
import torch


def add_metadata_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the EPUB metadata options.

    Every option takes a value that may contain the placeholders {filename}
    and {stem}, which are replaced with the name of the PDF being processed so
    that one command line can convert a whole directory.
    """
    parser.add_argument(
        '--title',
        type=str,
        default=None,
        help='Book title (default: the PDF file name)'
    )
    parser.add_argument(
        '--author',
        type=str,
        default=None,
        help='Author(s); separate several names with ";" to list them separately'
    )
    parser.add_argument(
        '--publisher',
        type=str,
        default=None,
        help='Publisher (default: PDF2EPUB)'
    )
    parser.add_argument(
        '--language',
        type=str,
        default=None,
        help='Language code, e.g. en, de, fr (default: en)'
    )
    parser.add_argument(
        '--rights',
        type=str,
        default=None,
        help='Rights statement (default: All rights reserved)'
    )
    parser.add_argument(
        '--identifier',
        type=str,
        default=None,
        help='Unique identifier (default: a stable UUID derived from the title)'
    )
    parser.add_argument(
        '--date',
        type=str,
        default=None,
        help='Publication date as YYYY-MM-DD (default: today)'
    )


def collect_metadata_args(args: argparse.Namespace) -> dict:
    """Turn the parsed metadata options into a mapping for build_metadata.

    Returns an empty mapping when none were supplied, which lets EPUB
    generation fall back to the interactive prompts.
    """
    values = {}
    for flag, _key in metadata_lib.METADATA_FIELDS:
        value = getattr(args, flag, None)
        if value is not None:
            values[flag] = value

    return values


def metadata_from_args(args: argparse.Namespace, pdf_path: Path) -> dict:
    """Validate the metadata options for one PDF, expanding placeholders."""
    return metadata_lib.build_metadata(collect_metadata_args(args), filename=str(pdf_path))


def stdin_is_interactive() -> bool:
    """True when stdin is a terminal that can still be prompted on."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def main():
    if torch.cuda.is_available():
        print("CUDA is available. Using GPU for processing.")
    elif torch.backends.mps.is_available():
        print("MPS is available. Using Apple Silicon for processing.")
    else:
        print("CUDA is not available. Using CPU for processing.")
        
    parser = argparse.ArgumentParser(
        description='Convert PDF files to EPUB format via Markdown'
    )
    parser.add_argument(
        'input_path',
        nargs='?',
        type=str,
        help='Path to input PDF file or directory (default: ./input/*.pdf)'
    )
    parser.add_argument(
        'output_path',
        nargs='?',
        type=str,
        help='Path to output directory (default: directory named after PDF)'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=None,
        help='Maximum number of pages to process'
    )
    parser.add_argument(
        '--start-page',
        type=int,
        default=None,
        help='Page number to start from'
    )
    parser.add_argument(
        '--skip-epub',
        action='store_true',
        help='Skip EPUB generation, only create markdown'
    )
    parser.add_argument(
        '--skip-md',
        action='store_true',
        help='Skip markdown generation, use existing markdown files'
    )
    parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Accept the default EPUB metadata instead of prompting for it'
    )
    add_metadata_arguments(parser)

    args = parser.parse_args()

    metadata_args = collect_metadata_args(args)

    if args.skip_epub and metadata_args:
        parser.error("metadata options are ignored with --skip-epub")

    # Reading metadata from stdin is only possible on a terminal. Batch runs
    # (cron, CI, piped input) would otherwise die with an EOFError partway
    # through a directory, so fall back to defaults with a warning instead.
    unattended = False
    if metadata_args or args.yes:
        unattended = True
    elif not args.skip_epub and not stdin_is_interactive():
        print(
            "Warning: stdin is not a terminal, so metadata cannot be asked for. "
            "Using defaults; pass --title/--author/... to set them.",
            file=sys.stderr,
        )
        unattended = True

    # Get input path
    input_path = Path(args.input_path) if args.input_path else pdf2md.get_default_input_dir()
    
    # Get queue of PDFs to process
    queue = pdf2md.add_pdfs_to_queue(input_path)
    print(f"Found {len(queue)} PDF files to process")

    # A date that cannot be parsed fails every file identically, so reject it
    # before doing the expensive PDF conversion work.
    if metadata_args and args.date is not None:
        try:
            metadata_lib.normalise_date(args.date)
        except metadata_lib.MetadataError as exc:
            parser.error(str(exc))
    
    # Process each PDF
    failed = []
    for pdf_path in queue:
        print(f"\nProcessing: {pdf_path.name}")
        
        # Get output directory for this PDF
        if args.output_path:
            output_path = Path(args.output_path)
            markdown_dir = output_path / pdf_path.stem
        else:
            markdown_dir = pdf2md.get_default_output_dir(pdf_path)
            output_path = markdown_dir.parent
            
        try:
            # Check if markdown directory exists when skipping MD generation
            if args.skip_md:
                if not markdown_dir.exists():
                    print(f"Error: Markdown directory not found: {markdown_dir}", file=sys.stderr)
                    failed.append(pdf_path.name)
                    continue
                print(f"Using existing markdown files from: {markdown_dir}")
                
            # Convert PDF to Markdown unless skipped
            if not args.skip_md:
                print("Converting PDF to Markdown...")
                pdf2md.convert_pdf(
                    str(pdf_path),
                    markdown_dir,
                    args.max_pages,
                    args.start_page,
                )
            
            # Convert Markdown to EPUB unless skipped
            if not args.skip_epub:
                epub_metadata = None
                if unattended:
                    try:
                        epub_metadata = metadata_from_args(args, pdf_path)
                    except metadata_lib.MetadataError as exc:
                        print(f"Error: {exc}", file=sys.stderr)
                        failed.append(pdf_path.name)
                        continue

                print("Converting Markdown to EPUB...")
                mark2epub.convert_to_epub(markdown_dir, output_path, metadata=epub_metadata)
                
        except Exception as e:
            print(f"Error processing {pdf_path.name}: {str(e)}", file=sys.stderr)
            failed.append(pdf_path.name)
            continue

    if failed:
        print(
            f"\nFailed to process {len(failed)} of {len(queue)} PDF file(s):",
            file=sys.stderr,
        )
        for name in failed:
            print(f"  - {name}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
