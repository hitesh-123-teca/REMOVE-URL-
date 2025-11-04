FROM python:3.10-slim

WORKDIR /app

# Install dependencies (with updated ntpsec-ntpdate)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    libsm6 \
    libxrender1 \
    libxext6 \
    ntpsec-ntpdate \
    tzdata \
 && rm -rf /var/lib/apt/lists/*

# Sync time once
RUN ntpdate -u time.google.com || true || ntpsec-ntpdate -u time.google.com || true

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install -r requirements.txt

COPY . .

# Final CMD ensures time sync every restart
CMD ntpdate -u time.google.com || ntpsec-ntpdate -u time.google.com || true && python3 bot.py
