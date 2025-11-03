FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (time sync fix)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    ffmpeg \
    libsm6 \
    libxrender1 \
    libxext6 \
    ntpsec-ntpdate \
 && rm -rf /var/lib/apt/lists/*

# Sync system time (important for Pyrogram)
RUN ntpdate -u time.google.com || true

# Upgrade pip
RUN pip install --upgrade pip

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy bot files
COPY . .

# Run time sync before starting the bot
CMD ntpdate -u time.google.com || true && python3 bot.py
