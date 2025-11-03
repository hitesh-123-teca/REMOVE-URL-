FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (without system time sync)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    ffmpeg \
    libsm6 \
    libxrender1 \
    libxext6 \
 && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy bot files
COPY . .

# Start the bot (no system ntpdate needed)
CMD python3 bot.py
