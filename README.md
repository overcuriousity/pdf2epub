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
  --start-page INT         Page number to start from
  --ocr-engine ENGINE      marker (default), unlimited or vllm
  --vllm-url URL           vLLM server for --ocr-engine vllm (default: http://localhost:8000/v1)
  --vllm-workers INT       Pages sent to the vLLM server at once (default: 8)
  --vllm-keep-server       Leave an auto-started vLLM server running afterwards
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

### Alternative OCR engines: Unlimited-OCR

For scanned PDFs, two engines use Baidu's
[Unlimited-OCR](https://github.com/baidu/Unlimited-OCR) vision-language model
instead of marker. Every page is rendered at 200 DPI and parsed by the model, so
they are not worth using on digital PDFs, where marker reads the embedded text
directly. Blocks the model labels as images are cropped from the render and
saved to `images/`.

- `--ocr-engine unlimited` loads the model in-process through transformers.
- `--ocr-engine vllm` sends the pages to a separate vLLM server, several at a
  time, so vLLM can batch them. This is by far the fastest option for scans.

Both need an NVIDIA GPU (no CPU or MPS support, so neither works in the CPU
Docker image). The model (~6.7 GB) is downloaded from HuggingFace on first use
and runs remote code from that repository (`trust_remote_code=True`).

#### Measured speed

Synthetic scanned book (A4 at 200 DPI, Indonesian text, one figure per page),
RTX 4060 8 GB that also drives the desktop, Fedora 44:

| Engine | 3 pages | 12 pages | Per page (12 pages) | GPU memory |
|---|---|---|---|---|
| marker (Surya) | 27 s | 71 s | ~5.9 s (~4 s OCR only) | ~7.3 GB |
| unlimited (transformers, bf16) | 61 s | 178 s | ~13.9 s | ~7.4 GB |
| vllm (FP8, 8 workers) | 9.5 s | 15.4 s | ~1.3 s | ~7.4 GB, held while the server runs |
| vllm (FP8, 12 workers) | – | 12.6 s | ~1.05 s | same |

Times for marker and unlimited include loading the models (~10 s). The vllm
times exclude starting the server, which takes about 2 minutes (the first start
also downloads the model), and the first batch after a start runs ~4 s slower.

Quality on these pages: all three read the text correctly. Unlimited-OCR kept
every heading, while marker dropped the repeated "Bagian N" section headings as
page headers. Unlimited-OCR leaves headings as plain text rather than `##` and
keeps the printed page numbers. The FP8 server misread one word ("rumitnya" as
"mutinya") once or twice in ~2,400 words, depending on how pages were batched;
the bf16 transformers engine did not.

On a real scanned book (Indonesian, 841 small pages of ~9.6 x 13.7 cm) the
vllm engine read 60 pages in 92 s (~1.5 s/page) with only occasional
single-letter errors. Before sending a page, the engine pads it with white to
exactly 2:3. vLLM otherwise splits pages that are slightly wider than 2:3 into
12 or more upscaled 640 px tiles, which ran the 8 GB card out of memory on half
of that book's pages.

#### `--ocr-engine unlimited` (transformers)

- Needs extra packages: `pip install addict easydict matplotlib torchvision`
  (torchvision must match your torch build).
- Peak VRAM is just under 8 GB. The engine sets
  `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`, without which an 8 GB
  card runs out of memory on Linux. Close other GPU-heavy apps.

```bash
python main.py scanned_book.pdf --ocr-engine unlimited
```

#### `--ocr-engine vllm` (vLLM server, Linux)

The client only needs `requests`, which marker already installs. The model runs
in vLLM's dedicated image (the architecture is not in the regular vLLM wheel),
following the [vLLM recipe](https://recipes.vllm.ai/baidu/Unlimited-OCR).

GPU access from Podman needs the NVIDIA Container Toolkit and a CDI spec (on
Fedora, add NVIDIA's repo from `https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo`
to `/etc/yum.repos.d/`, then run `sudo dnf install nvidia-container-toolkit` and
`sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml`). Then:

```bash
python main.py scanned_book.pdf --ocr-engine vllm
```

If no server answers at `--vllm-url` and the URL is local, the program starts
one itself in a Podman container named `pdf2epub-vllm`, waits until it is ready
(about 2 minutes; the first run also pulls the ~19 GB image and the model), and
stops it when all PDFs are done, on errors and on Ctrl+C too. The server holds
most of the GPU memory, so it is not left running. Pass `--vllm-keep-server` to
leave it running for the next run, which then starts right away; stop it with
`podman stop pdf2epub-vllm`. A server that was already running is used as is and
left alone.

To run the server yourself instead (for example on another machine, with
`--vllm-url` pointing at it), this is the command the program uses:

```bash
podman run --rm --device nvidia.com/gpu=all --security-opt label=disable \
  --network host --ipc host \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -v ~/.cache/vllm:/root/.cache/vllm \
  docker.io/vllm/vllm-openai:unlimited-ocr \
  baidu/Unlimited-OCR \
  --trust-remote-code \
  --logits_processors vllm.model_executor.models.unlimited_ocr:NGramPerReqLogitsProcessor \
  --no-enable-prefix-caching \
  --mm-processor-cache-gb 0 \
  --quantization fp8 --gpu-memory-utilization 0.85 \
  --max-model-len 8192 --skip-mm-profiling
```

It is ready once `curl localhost:8000/v1/models` answers.

Notes on the server flags:

- `--security-opt label=disable` lets rootless Podman open the GPU under
  SELinux; without it `nvidia-smi` in the container fails with "Insufficient
  Permissions". With Docker, use `--gpus all` instead of `--device` and drop
  `--security-opt`.
- The last three lines are for 8 GB cards. In bf16 the weights take 6.2 GB, and
  each page needs another ~400 MB for the vision encoder, which does not fit
  next to a KV cache. `--quantization fp8` (RTX 40xx or newer) halves the
  weights and leaves room for ~33k tokens of KV cache, enough for ~12 pages in
  flight. `--skip-mm-profiling` is needed because vLLM would otherwise profile a
  32-tile image, far larger than an A4 page (1 global view + 6 tiles). On a
  GPU with 16 GB or more, drop these three lines to run the model in bf16
  (for the auto-started server, edit `VLLM_ARGS` in `modules/vllm_ocr.py`).
- The two cache mounts keep the weights and vLLM's compiled kernels between
  runs. On an 8 GB card, stop the server before running marker or the
  transformers engine; it holds the GPU memory while it runs.
- If the server is not reachable and cannot be started automatically (a remote
  `--vllm-url`, or no `podman`), `--ocr-engine vllm` stops with an error that
  prints this command. If the container exits while starting, the error shows
  its last log lines.

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
