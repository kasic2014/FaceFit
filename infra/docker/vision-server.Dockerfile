FROM python:3.10-slim

RUN apt-get update && apt-get install -y libgl1-mesa-glx libglib2.0-0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY ai-server/vision-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ai-server/vision-server /app

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
