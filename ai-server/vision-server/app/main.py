from fastapi import FastAPI

app = FastAPI(title="Face-Fit Vision Server", version="1.0.0")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "vision-server"}
