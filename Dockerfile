FROM python:3.10-slim

WORKDIR /app

# Install updated dependencies (ntpsec-ntpdate replaces ntpdate)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    libsm6 \
    libxrender1 \
    libxext6 \
    ntpsec-ntpdate \
    tzdata \
 && rm -rf /var/lib/apt/lists/*

# Initial time sync
RUN ntpdate -u time.google.com || ntpsec-ntpdate -u time.google.com || true

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install -r requirements.txt

COPY . .

# Start command ensures fresh time sync
CMD ntpdate -u time.google.com || ntpsec-ntpdate -u time.google.com || true && python3 bot.py
