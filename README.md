# PDF2EPUB 📚

Convert PDF files to nicely structured Markdown and EPUB format with intelligent layout detection.

## ✨ Features

- 📖 Smart layout detection for books and academic papers
- 🔍 Advanced text extraction and OCR capabilities
- 📊 Table detection and formatting
- 🖼️ Image extraction and optimization
- 📝 Clean markdown output with preserved structure
- 📱 EPUB generation with customizable styling
- 🌍 Multi-language support
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
python -m pip install -r requirements.txt
```

Keep the virtual environment active when running `python main.py`. If you see
`ModuleNotFoundError: No module named 'latex2mathml'`, your Python may be using
another environment. On Linux/Mac, run with the project interpreter directly:

```bash
.venv/bin/python main.py ~/scan-pages/Book1.pdf
```

If that interpreter also reports a missing dependency, install the full
requirements into `.venv`. For environments created with uv, use
`uv pip install --python .venv/bin/python -r requirements.txt`.

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
docker run -it --rm \
  -v "$(pwd)":/data \
  -v pdf2epub-models:/models \
  pdf2epub input.pdf
```

`-it` is required for EPUB generation because metadata is prompted
interactively; with `--skip-epub` it can run non-interactively.

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
and so on; press Enter to accept each default). It therefore needs a terminal —
run it non-interactively and it will fail with `EOFError`. Use `--skip-epub` to
produce only markdown without any prompts.

### Advanced Options

```bash
python main.py [input_path] [output_path] [options]

Options:
  --max-pages INT          Maximum number of pages to process
  --start-page INT         Zero-based page index to start from
  --chunk-pages INT        Pages processed at once (default: 10; 0 disables chunking)
  --skip-epub              Skip EPUB generation, only create markdown
  --skip-md                Skip markdown generation, use existing markdown files
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

### GPU memory usage

PDFs are processed in 10-page chunks by default, then joined into one Markdown
file and one EPUB. This bounds the page-image memory used by Marker; users do
not need to split or reassemble the PDF themselves. On an 8 GB GPU, the default
also sets all of Marker's layout, detection, OCR, recognition, table, and
equation batch sizes to 1.

If a particularly image-heavy PDF still runs out of memory, use a smaller
chunk (for example `--chunk-pages 4`). `PDF2EPUB_GPU_BATCH_SIZE` can raise the
model batch sizes on GPUs with more memory. `DETECTOR_BATCH_SIZE` alone does not
control Marker's internal detection batch in the pinned Marker version.

PyTorch's allocator variable is named `PYTORCH_CUDA_ALLOC_CONF` (including
`CUDA`), for example:

```bash
PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True python main.py book.pdf
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
