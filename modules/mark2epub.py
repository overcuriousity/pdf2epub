#!/usr/bin/env python3
"""
High-fidelity EPUB 3 compilation module using Pandoc.
Replaces the legacy pipeline with robust MathML compilation and semantic splitting.
"""

from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import regex as re
from typing import Optional, Dict, Any

DEFAULT_EPUB_CSS = """@charset "UTF-8";

body {
    font-family: -apple-system, BlinkMacSystemFont, "Charter", "Georgia", "Palatino", serif;
    line-height: 1.6;
    margin: 4% 5%;
}

h1, h2, h3, h4, h5, h6 {
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", "Arial", sans-serif;
    font-weight: 600;
    line-height: 1.25;
    margin-top: 1.6em;
    margin-bottom: 0.5em;
    page-break-after: avoid;
    break-after: avoid;
}

h1 { font-size: 1.8rem; }
h2 { font-size: 1.4rem; }
h3 { font-size: 1.2rem; }

p {
    margin: 0 0 0.8em 0;
    text-align: justify;
    text-justify: inter-word;
    text-indent: 1.5em;
    orphans: 2;
    widows: 2;
    hyphens: auto;
    -webkit-hyphens: auto;
}

h1 + p, h2 + p, h3 + p, h4 + p, hr + p, blockquote + p {
    text-indent: 0;
}

img {
    max-width: 100%;
    height: auto;
    display: block;
    margin: 1.2em auto;
}

pre, code {
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 0.85em;
}

pre {
    padding: 0.8em;
    overflow-x: auto;
    border-radius: 4px;
    background: rgba(128, 128, 128, 0.12);
    white-space: pre-wrap;
    word-break: break-all;
}

code {
    padding: 0.2em 0.4em;
    background: rgba(128, 128, 128, 0.12);
    border-radius: 3px;
}

pre code {
    padding: 0;
    background: transparent;
}

blockquote {
    margin: 1.2em 0 1.2em 1.5em;
    padding-left: 1em;
    border-left: 3px solid rgba(128, 128, 128, 0.4);
    font-style: italic;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 1.5em 0;
    font-size: 0.9em;
}

th, td {
    border: 1px solid rgba(128, 128, 128, 0.3);
    padding: 0.5em 0.8em;
}

th {
    background: rgba(128, 128, 128, 0.1);
}

.math-display {
    display: block;
    margin: 1.2em 0;
    overflow-x: auto;
    text-align: center;
}

.math-inline {
    display: inline;
}
"""

class PandocNotFoundError(RuntimeError):
    pass

def check_pandoc_installed() -> str:
    pandoc_path = shutil.which("pandoc")
    if not pandoc_path:
        raise PandocNotFoundError(
            "\n[CRITICAL ERROR] Pandoc not found in system PATH.\n"
            "To run outside Docker, install Pandoc 3.x:\n"
            "  - macOS: brew install pandoc\n"
            "  - Ubuntu/Debian: sudo apt-get install pandoc\n"
            "  - Windows: winget install JohnMacFarlane.Pandoc\n"
            "Or run via the official project Docker image."
        )
    return pandoc_path

def sanitize_math_syntax(text: str) -> str:
    """
    Fix archaic marker-pdf TeX constructs (such as \\rm)
    that cause failures in Pandoc's MathML parser.
    """
    text = re.sub(r'\{\\rm\s+([^}]+)\}', r'\\mathrm{\1}', text)
    text = re.sub(r'\\rm\s+([a-zA-Z0-9]+)', r'\\mathrm{\1}', text)
    text = re.sub(r'\\rm\b', r'\\mathrm', text)
    return text

def resolve_metadata(markdown_dir: Path, md_path: Path) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "title": md_path.stem.replace("_", " ").title(),
        "creator": "Unknown Author",
        "language": "en",
        "publisher": "PDF2EPUB"
    }

    desc_file = markdown_dir / "description.json"
    if desc_file.exists():
        try:
            with open(desc_file, "r", encoding="utf-8") as f:
                data = json.load(f).get("metadata", {})
                if data.get("dc:title"): metadata["title"] = data["dc:title"]
                if data.get("dc:creator"): metadata["creator"] = data["dc:creator"]
                if data.get("dc:language"): metadata["language"] = data["dc:language"]
        except Exception:
            pass

    # If in an interactive terminal, allow confirmation/editing
    if sys.stdin.isatty():
        prompt = input(f"Book Title [{metadata['title']}]: ").strip()
        if prompt: metadata["title"] = prompt
        author = input(f"Author(s) [{metadata['creator']}]: ").strip()
        if author: metadata["creator"] = author

    return metadata

def find_cover_image(images_dir: Path) -> Optional[Path]:
    """Dynamically identifies the best candidate for cover image (returns absolute path)."""
    if not images_dir.exists():
        return None

    # 1. Look for files with explicit cover names
    for f in images_dir.iterdir():
        if f.is_file() and "cover" in f.name.lower() and f.suffix.lower() in [".jpg", ".jpeg", ".png"]:
            return f.resolve()

    # 2. Search for any image generated from page 0 of the PDF (sorted numerically)
    page_zero_candidates = sorted(
        [f for f in images_dir.iterdir() if f.is_file() and f.name.startswith("_page_0_") and f.suffix.lower() in [".jpg", ".jpeg", ".png"]],
        key=lambda x: x.name
    )
    if page_zero_candidates:
        return page_zero_candidates[0].resolve()

    return None

def convert_to_epub(markdown_dir: Path, output_path: Path) -> None:
    """
    Compiles artifacts generated by Marker into an EPUB 3 file using Pandoc.
    Maintains strict compatibility with main.py invocations.
    """
    check_pandoc_installed()

    # Normalize markdown_dir to absolute path from the start
    markdown_dir = Path(markdown_dir).resolve()
    if not markdown_dir.exists() or not markdown_dir.is_dir():
        raise FileNotFoundError(f"Markdown directory not found: {markdown_dir}")

    md_files = sorted(list(markdown_dir.glob("*.md")))
    if not md_files:
        raise ValueError(f"No .md files found in: {markdown_dir}")

    primary_md = md_files[0]

    # Normalize destination to absolute path
    output_path = Path(output_path).resolve()
    if output_path.is_dir() or not output_path.suffix:
        output_path.mkdir(parents=True, exist_ok=True)
        epub_target = (markdown_dir / f"{markdown_dir.name}.epub").resolve()
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        epub_target = output_path.resolve()

    # Sanitize Markdown in a temporary file
    raw_content = primary_md.read_text(encoding="utf-8")
    sanitized_content = sanitize_math_syntax(raw_content)

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as tmp_md, \
         tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".css", delete=False) as tmp_css:
        
        tmp_md_path = Path(tmp_md.name).resolve()
        tmp_css_path = Path(tmp_css.name).resolve()

        tmp_md.write(sanitized_content)
        tmp_md.flush()

        tmp_css.write(DEFAULT_EPUB_CSS)
        tmp_css.flush()

    try:
        meta = resolve_metadata(markdown_dir, primary_md)
        images_dir = (markdown_dir / "images").resolve()

        cmd = [
            "pandoc",
            str(tmp_md_path),
            "-o", str(epub_target),
            "-f", "markdown+smart",
            "-t", "epub3",
            "--split-level=2",
            "--toc",
            "--toc-depth=3",
            "--math-method=mathml",  # Official Pandoc 3.x syntax without deprecation warning
            f"--resource-path=.:images:{markdown_dir}:{images_dir}",
            f"--css={tmp_css_path}",
            "-M", f"title={meta['title']}",
            "-M", f"author={meta['creator']}",
            "-M", f"lang={meta['language']}",
            "-M", f"publisher={meta['publisher']}"
        ]

        cover_img = find_cover_image(images_dir)
        if cover_img and cover_img.exists():
            cmd.append(f"--epub-cover-image={cover_img}")

        print(f"\n[Pandoc] Starting EPUB 3 compilation: {epub_target.name}")
        result = subprocess.run(
            cmd,
            cwd=str(markdown_dir),
            capture_output=True,
            text=True,
            check=True
        )
        if result.stderr:
            print(f"[Pandoc Warning]:\n{result.stderr}", file=sys.stderr)

        print(f"[Pandoc] EPUB 3 generated successfully: {epub_target}")

    except subprocess.CalledProcessError as e:
        print(f"[Pandoc ERROR]: Compilation failed.\n{e.stderr}", file=sys.stderr)
        raise
    finally:
        if tmp_md_path.exists(): tmp_md_path.unlink()
        if tmp_css_path.exists(): tmp_css_path.unlink()