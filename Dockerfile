FROM python:3.13-slim

WORKDIR /app

# 1. Install Pandoc natively and cleanly
RUN apt-get update && \
    apt-get install -y --no-install-recommends pandoc && \
    rm -rf /var/lib/apt/lists/*

# 2. Python dependencies (leverages build cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Application code
COPY main.py .
COPY modules/ modules/

ENV HF_HOME=/models
VOLUME /models

WORKDIR /data

ENTRYPOINT ["python", "/app/main.py"]