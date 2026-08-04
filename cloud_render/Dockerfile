FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY cloud_render/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY cloud_render/worker.py ./worker.py

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/worker.py"]
