FROM python:3.10-slim AS egl-dispatcher

WORKDIR /tmp/egl
RUN apt-get update \
    && apt-get download libegl1 \
    && mkdir /extracted \
    && dpkg-deb --extract libegl1_*.deb /extracted

FROM python:3.10-slim AS dependencies

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY ai-server/analysis-server/requirements.txt \
    ai-server/analysis-server/requirements-cpu.txt ./
RUN pip install -r requirements-cpu.txt \
    && pip uninstall --yes opencv-contrib-python \
    && pip install --no-deps --force-reinstall \
        opencv-contrib-python-headless==5.0.0.93

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgles2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=egl-dispatcher \
    /extracted/usr/lib/x86_64-linux-gnu/libEGL.so.1.1.0 \
    /usr/lib/x86_64-linux-gnu/libEGL.so.1.1.0
RUN ln -s libEGL.so.1.1.0 /usr/lib/x86_64-linux-gnu/libEGL.so.1

COPY ai-server/analysis-server/scripts/download_cv_models.py /tmp/download_cv_models.py
RUN python /tmp/download_cv_models.py --output /app/models \
    && rm /tmp/download_cv_models.py

FROM dependencies AS test

WORKDIR /workspace/ai-server/analysis-server
COPY ai-server/analysis-server ./
COPY ai-server/openapi /workspace/ai-server/openapi
ENV MPLCONFIGDIR=/tmp/matplotlib
USER nobody
CMD ["python", "-m", "unittest", "tests.test_analysis_http_api", "tests.test_analysis_api_settings", "tests.test_stt_http_analyzer", "tests.test_cv_analyzer", "tests.test_media_download", "-v"]

FROM dependencies AS runtime

RUN groupadd --system facefit \
    && useradd --system --gid facefit --create-home facefit \
    && mkdir -p /app/data/temp \
    && chown -R facefit:facefit /app/data/temp

COPY --chown=facefit:facefit ai-server/analysis-server/app /app/app

USER facefit
EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2).read()"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
