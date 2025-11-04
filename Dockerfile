FROM python:3.10-slim

WORKDIR /app

# Install system dependencies + ntpdate for time sync
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    ffmpeg \
    libsm6 \
    libxrender1 \
    libxext6 \
    ntpdate \
 && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy bot files
COPY . .

# Sync time before starting the bot
CMD ntpdate -s time.google.com && python3 bot.py
