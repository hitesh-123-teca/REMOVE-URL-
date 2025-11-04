FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    libsm6 \
    libxrender1 \
    libxext6 \
    ntpdate \
    tzdata \
 && rm -rf /var/lib/apt/lists/*

RUN ntpdate -u time.google.com || true

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install -r requirements.txt

COPY . .

CMD ntpdate -u time.google.com || true && python3 bot.py
