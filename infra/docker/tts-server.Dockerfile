FROM python:3.10-slim

WORKDIR /app

COPY ai-server/tts-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai-server/tts-server /app

EXPOSE 8003

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
