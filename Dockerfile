# Use lightweight Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies and sync time
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    ffmpeg \
    libsm6 \
    libxrender1 \
    libxext6 \
    tzdata \
    ntpsec-ntpdate && ntpdate -u time.google.com && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Set timezone (optional)
ENV TZ=Asia/Kolkata

# Run the bot
CMD ["python3", "main.py"]
