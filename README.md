# PDF2EPUB 📚

Convert PDF files to nicely structured Markdown and EPUB format with intelligent layout detection.

## ✨ Features

- 📖 Smart layout detection for books and academic papers
- 🔍 Advanced text extraction and OCR capabilities
- 📊 Table detection and formatting
- 🖼️ Image extraction and optimization
- 📝 Clean markdown output with preserved structure
- 📱 EPUB generation with customizable styling
- 🌐 Multi-language support
- ⚡ Non-interactive batch conversion with CLI metadata options
- 🚀 GPU acceleration support (NVIDIA & AMD)
- 🍎 Apple Silicon support

## 🛠️ Dependencies

- Python 3.10–3.14 (3.13 recommended, see below)
- PyTorch (with CUDA/ROCm support for GPU acceleration)
- marker-pdf==1.10.2
- transformers==4.57.6
- markdown==3.10.2
- latex2mathml==3.81.0

### ⚠️ Python version

Python 3.13 is recommended.

`marker-pdf` constrains `Pillow<11.0.0`, and Pillow only ships Python 3.14
wheels from 11.3.0 onward. On Python 3.10–3.13 every dependency installs as a
prebuilt wheel. On 3.14, pip has to build Pillow from source instead: this
works, but it is slower and requires a working C toolchain plus the image
library headers Pillow links against. On Debian/Ubuntu install them first:

```bash
sudo apt install libjpeg-dev zlib1g-dev libtiff-dev libfreetype6-dev libwebp-dev
```

Without these headers the install fails with
`RequiredDependencyException: The headers or library files could not be found for jpeg`.

## 💻 Installation

1. Create and activate a virtual environment.

On Linux/Mac:
```bash
python3.13 -m venv .venv
source .venv/bin/activate
```

On Windows:
```powershell
py -3.13 -m venv .venv
.venv\Scripts\activate
```

2. Install Python dependencies (this installs PyTorch as well):
```bash
pip install -r requirements.txt
```

3. GPU acceleration (optional):

PyTorch is installed as a dependency in step 2. On Apple Silicon that wheel
already supports MPS, so no further action is needed. For a specific CUDA or
ROCm build, reinstall PyTorch using the selector at
[pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/).
For example, for AMD GPUs with ROCm:
```bash
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2
```

4. Verify GPU support:
```python
import torch
print(torch.__version__)  # PyTorch version
print(torch.cuda.is_available())  # Should return True for NVIDIA
print(torch.backends.mps.is_available())  # Should return True for Apple Silicon
print(torch.version.hip)  # Should print ROCm version for AMD
```

### 🐳 Docker

A CPU-only image can be built from the included `Dockerfile`:

```bash
docker build -t pdf2epub .
```

Run it with your PDFs mounted at `/data` and a model cache volume (marker-pdf
downloads its models on first run):

```bash
docker run --rm \
  -v "$(pwd)":/data \
  -v pdf2epub-models:/models \
  pdf2epub input.pdf
```

Metadata is prompted for interactively when a terminal is attached. Without
one, pdf2epub warns and falls back to defaults, so `-it` is optional. Passing
any of the metadata options (`--title`, `--author`, …) sets them explicitly and
skips the prompts entirely:

```bash
docker run --rm \
  -v "$(pwd)":/data \
  -v pdf2epub-models:/models \
  pdf2epub input.pdf --title "Dune" --author "Frank Herbert"
```

Tagged releases are also published to
`ghcr.io/overcuriousity/pdf2epub` by the Docker workflow.

## 🚀 Usage

### Basic Usage

Convert a single PDF file:
```bash
python main.py input.pdf
```

Convert all PDFs in a directory:
```bash
python main.py input_directory/
```

EPUB generation prompts interactively for metadata (title, author, language,
and so on; press Enter to accept each default). When a terminal is available
you can answer those prompts; otherwise pdf2epub prints a warning and uses the
default metadata, so nothing fails for lack of a TTY. Use `--skip-epub` to
produce only markdown without any prompts, or supply the metadata options below
to set the values directly (see [Batch processing](#batch-processing)).

### Metadata Options

Every EPUB metadata value can be set on the command line, which makes
non-interactive and batch conversion possible:

```bash
python main.py book.pdf --title "Dune" --author "Frank Herbert" --publisher "Ace"
```

| Option | Description | Default |
| --- | --- | --- |
| `--title` | Book title | The PDF file name |
| `--author` | Author(s); separate several names with `;` | `Unknown Author` |
| `--publisher` | Publisher | `PDF2EPUB` |
| `--language` | Language code, e.g. `en`, `de`, `fr` | `en` |
| `--rights` | Rights statement | `All rights reserved` |
| `--identifier` | Unique identifier | A stable UUID derived from the title |
| `--date` | Publication date as `YYYY-MM-DD` | Today |
| `-y`, `--yes` | Accept the defaults for everything not given | — |

Notes:

- `--author "Jane Doe; John Roe"` records two separate `dc:creator` entries.
  Commas are not treated as separators, so `"Doe, Jane"` stays one name.
- The title defaults to the PDF's file name rather than `Untitled Document`,
  so a batch run stays legible.
- `--identifier` is derived from the title and file name, so re-running the
  same conversion reproduces the same identifier instead of generating a new
  one each time.

### Batch Processing

`--title` and `--author` accept the placeholders `{filename}` (with extension)
and `{stem}` (without). They are filled in per file, so one command converts a
whole directory without the metadata being copied between books:

```bash
python main.py ./input/ --title "{stem}" --author "Unknown Author"
```

The PDF file name is also used to derive a unique `dc:identifier` per book.

Running without a terminal (cron, CI, piped input) no longer crashes with
`EOFError`: pdf2epub prints a warning and falls back to the defaults above.
Supply the metadata options to control the values, or `-y` to accept the
defaults deliberately.

### Advanced Options

```bash
python main.py [input_path] [output_path] [options]

Options:
  --max-pages INT          Maximum number of pages to process
  --start-page INT         Page number to start from
  --skip-epub              Skip EPUB generation, only create markdown
  --skip-md                Skip markdown generation, use existing markdown files
  --title STR              Book title (supports {stem} and {filename})
  --author STR             Author(s); separate several names with ";"
  --publisher STR          Publisher
  --language STR           Language code, e.g. en, de, fr
  --rights STR             Rights statement
  --identifier STR         Unique identifier
  --date STR               Publication date as YYYY-MM-DD
  -y, --yes                Accept default metadata instead of prompting
```

If `input_path` is omitted, all PDFs in `./input/` are processed.

### Examples

Process a specific range of pages:
```bash
python main.py book.pdf --start-page 10 --max-pages 50
```

Convert to markdown only:
```bash
python main.py thesis.pdf --skip-epub
```

Convert a directory unattended, one book per command:
```bash
python main.py ./books/ --title "{stem}" --author "Unknown Author" \
  --publisher "Archive.org" --language en < /dev/null
```

### Tests

```bash
pip install pytest
pytest tests/
```

### Output Structure

```
output_directory/
├── document_name/
│   ├── document_name.md
│   ├── document_name.epub
│   ├── document_name_metadata.json
│   └── images/
│       ├── image1.png
│       ├── image2.jpg
│       └── ...
```

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

1. Fork the repository
2. Create a new branch for your feature
3. Commit your changes
4. Push to your branch
5. Create a Pull Request

Please ensure your code follows the existing style and includes appropriate tests.

### Development Setup

1. Clone the repository:
```bash
git clone https://github.com/overcuriousity/pdf2epub.git
cd pdf2epub
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install development dependencies:
```bash
pip install -r requirements.txt
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🐛 Known Issues

- Some image embedding might need manual adjustment
- Some complex mathematical equations might not be perfectly converted
- Certain PDF layouts with multiple columns may require manual adjustment
- Font detection might be imperfect in some cases

## 🙏 Acknowledgments

This project builds upon several excellent open-source libraries:
- [marker-pdf](https://github.com/VikParuchuri/marker) for PDF processing
- [mark2epub](https://github.com/AlexPof/mark2epub) for markdown conversion
- [PyTorch](https://pytorch.org/) for GPU acceleration
- [Transformers](https://huggingface.co/transformers) for advanced text processing
