FROM python:3.12-slim

# OpenCV runtime needs libGL/glib even with the headless wheel on some bases.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN mkdir -p data/videos data/frame_cache

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
