#!/usr/bin/env bash
# Run the fork's PDF converter in a disposable container (local Docker daemon).
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: pdf2epub.sh INPUT [OUTPUT_DIR] [PDF2EPUB_OPTIONS...]

INPUT is a host PDF file or directory of PDFs.
OUTPUT_DIR defaults to ./output; results go into OUTPUT_DIR/<pdf-stem>/.
All remaining arguments are forwarded unchanged to pdf2epub.
Runs unattended (--yes), removes the container on exit, and keeps the model cache.

Examples:
  pdf2epub.sh "./Dune.pdf" ./converted --title "Dune" --author "Frank Herbert"
  pdf2epub.sh ./books ./converted --title '{stem}' --author "Unknown Author"
  pdf2epub.sh ./book.pdf --max-pages 20 --language en
  pdf2epub.sh ./book.pdf --skip-epub

Environment overrides:
  PDF2EPUB_IMAGE      Default: ghcr.io/forceconstant/pdf2epub:0.1.0
  PDF2EPUB_CACHE_DIR  Default: ${XDG_CACHE_HOME:-$HOME/.cache}/pdf2epub

Requires Bash and Docker. Run on the machine hosting your Docker daemon;
input, output, and cache paths are bind-mounted from that machine.
The image is CPU-only. Models download on first use and are reused afterward.
EOF
}

fail() { printf 'pdf2epub: %s\n' "$*" >&2; exit 1; }

if [[ $# -eq 0 ]]; then usage >&2; exit 2; fi
if [[ $1 == --help || $1 == -h ]]; then usage; exit 0; fi
command -v docker >/dev/null 2>&1 || fail 'Docker was not found in PATH.'

input=$1
shift
output=./output
if [[ $# -gt 0 && $1 != -* ]]; then
  output=$1
  shift
fi
# Optional separator before the converter's flags.
if [[ $# -gt 0 && $1 == -- ]]; then shift; fi

if [[ -d $input ]]; then
  input_mount=$(cd -- "$input" && pwd -P)
  container_input=/input
elif [[ -f $input ]]; then
  [[ $input == *.[pP][dD][fF] ]] || fail "Input is not a PDF: $input"
  input_mount=$(cd -- "$(dirname -- "$input")" && pwd -P)
  container_input="/input/$(basename -- "$input")"
else
  fail "Input file or directory does not exist: $input"
fi

image=${PDF2EPUB_IMAGE:-ghcr.io/forceconstant/pdf2epub:0.1.0}
cache=${PDF2EPUB_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/pdf2epub}
mkdir -p -- "$output" "$cache"
output_mount=$(cd -- "$output" && pwd -P)
cache_mount=$(cd -- "$cache" && pwd -P)
[[ -w $output_mount ]] || fail "Output directory is not writable: $output_mount"
[[ -w $cache_mount ]] || fail "Model cache is not writable: $cache_mount"

printf 'Image: %s\nOutput: %s\nModel cache: %s\n' \
  "$image" "$output_mount" "$cache_mount" >&2

# Arrays/quoted arguments preserve spaces, semicolons, and literal placeholders.
# Use your UID/GID so generated files are not owned by root.
# No -it: --yes intentionally makes metadata generation non-interactive.
exec docker run --rm --init \
  --user "$(id -u):$(id -g)" \
  --volume "$input_mount:/input:ro" \
  --volume "$output_mount:/output" \
  --volume "$cache_mount:/models" \
  --env HOME=/models \
  --env XDG_CACHE_HOME=/models/cache \
  --env HF_HOME=/models/huggingface \
  --env TORCH_HOME=/models/torch \
  "$image" "$container_input" /output --yes "$@"
