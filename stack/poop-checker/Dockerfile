FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    OPENCV_FFMPEG_CAPTURE_OPTIONS="rtsp_transport;tcp"

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

CMD ["python", "app.py"]
