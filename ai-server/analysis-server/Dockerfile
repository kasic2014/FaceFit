FROM python:3.12.10-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models/faster-whisper \
    HF_HUB_OFFLINE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-api.txt requirements-stt.txt requirements-speech.txt requirements-docker.txt ./
RUN pip install --no-cache-dir -r requirements-docker.txt

RUN groupadd --system facefit \
    && useradd --system --gid facefit --home-dir /app facefit

COPY --chown=facefit:facefit . .
RUN mkdir -p \
        /app/data/output/analysis_api/jobs \
        /app/data/output/analysis_api/locks \
        /app/data/output/analysis_docker_validation \
    && chown -R facefit:facefit /app/data/output

EXPOSE 8002

USER facefit

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/health', timeout=3).read()"]

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
