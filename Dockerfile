FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng \
    libgl1 libglib2.0-0 chromium chromium-driver ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[ai-light,browser,audio]" \
 && playwright install --with-deps chromium
# Variante GPU (train + inference rapides) : base nvidia/cuda + pip install ".[gpu]"
#   FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 ... (voir README section GPU)

EXPOSE 7888
CMD ["python", "-m", "nocaptcha", "serve", "--host", "0.0.0.0", "--port", "7888"]
