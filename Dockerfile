FROM python:3.9-slim

WORKDIR /app

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install minimal FFmpeg (no heavy GUI libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create temp directory
RUN mkdir -p /tmp/wm_bot

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Expose health port for Koyeb health-check
EXPOSE 8080

# Start Gunicorn (serve Flask health_app) in background and then run bot
CMD ["sh", "-c", "gunicorn -k gevent -w 2 --bind 0.0.0.0:8080 'bot:health_app' & python bot.py"]
