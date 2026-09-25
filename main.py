#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
import modules.pdf2md as pdf2md
import modules.mark2epub as mark2epub
import torch
                


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
        '--ocr-engine',
        choices=['marker', 'unlimited', 'vllm'],
        default='marker',
        help='OCR backend: marker (default), unlimited (Baidu Unlimited-OCR '
             'in-process, NVIDIA GPU only) or vllm (Unlimited-OCR served by a '
             'running vLLM server); the last two are meant for scanned PDFs'
    )
    parser.add_argument(
        '--vllm-url',
        default='http://localhost:8000/v1',
        help='Base URL of the vLLM server for --ocr-engine vllm '
             '(default: http://localhost:8000/v1)'
    )
    parser.add_argument(
        '--vllm-workers',
        type=int,
        default=8,
        help='Pages sent to the vLLM server at once (default: 8)'
    )
    parser.add_argument(
        '--vllm-keep-server',
        action='store_true',
        help='Leave the vLLM server running afterwards if this run started it'
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
    
    args = parser.parse_args()
    
    # Get input path
    input_path = Path(args.input_path) if args.input_path else pdf2md.get_default_input_dir()
    
    # Get queue of PDFs to process
    queue = pdf2md.add_pdfs_to_queue(input_path)
    print(f"Found {len(queue)} PDF files to process")
    
    # The vllm engine needs a running server; start one in podman if needed
    # and stop it again at the end, since it holds most of the GPU memory.
    server_started = False
    if args.ocr_engine == 'vllm' and not args.skip_md:
        import modules.vllm_ocr as vllm_ocr
        try:
            server_started = vllm_ocr.start_server(args.vllm_url)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    failed = []
    try:
        # Process each PDF
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
                    extra = {}
                    if args.ocr_engine == 'unlimited':
                        import modules.unlimited_ocr as converter
                    elif args.ocr_engine == 'vllm':
                        import modules.vllm_ocr as converter
                        extra = {
                            'base_url': args.vllm_url,
                            'workers': args.vllm_workers,
                        }
                    else:
                        converter = pdf2md
                    converter.convert_pdf(
                        str(pdf_path),
                        markdown_dir,
                        args.max_pages,
                        args.start_page,
                        **extra,
                    )
            
                # Convert Markdown to EPUB unless skipped
                if not args.skip_epub:
                    print("Converting Markdown to EPUB...")
                    mark2epub.convert_to_epub(markdown_dir, output_path)
                
            except Exception as e:
                print(f"Error processing {pdf_path.name}: {str(e)}", file=sys.stderr)
                failed.append(pdf_path.name)
                continue
    finally:
        if server_started and not args.vllm_keep_server:
            vllm_ocr.stop_server()

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