FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# system deps for ffmpeg and opencv
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /tmp/wm_bot/download /tmp/wm_bot/out

# Default processing behavior (override via ENV if needed)
ENV WATERMARK_METHOD=delogo
ENV WATERMARK_PARAMS="x=iw-160:y=ih-60:w=150:h=50"
ENV MAX_FILE_SIZE=500000000

CMD ["python", "bot.py"]
