FROM python:3.9-slim

WORKDIR /app

# Install system dependencies (ffmpeg + build deps for gevent/opencv)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    gcc \
    libffi-dev \
    libssl-dev \
    pkg-config \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Create temp directory
RUN mkdir -p /tmp/wm_bot

# Set environment variables for better Python performance
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose health port (optional, Koyeb uses health TCP check)
EXPOSE 8080

# Start Gunicorn (serve Flask health_app) in background and then run bot
CMD ["sh", "-c", "gunicorn -k gevent -w 2 --bind 0.0.0.0:8080 'bot:health_app' & python bot.py"]
