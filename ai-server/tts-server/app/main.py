from fastapi import FastAPI

app = FastAPI(title="Face-Fit TTS Server", version="1.0.0")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "tts-server"}
