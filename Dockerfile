# CPU-only image. For GPU acceleration install a CUDA/ROCm PyTorch build
# instead (see README) or run natively.
FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY modules/ modules/

# marker-pdf downloads its models on first run; mount a volume at this path
# to cache them across container runs.
ENV HF_HOME=/models
VOLUME /models

# PDFs are read from /data/input and results written next to them by default.
WORKDIR /data

ENTRYPOINT ["python", "/app/main.py"]
