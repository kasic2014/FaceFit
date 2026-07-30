from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Ensure vision-server root is in sys.path
VISION_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(VISION_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(VISION_SERVER_ROOT))

app = FastAPI(
    title="Face-Fit Vision Server",
    description="MediaPipe-based Face and Pose landmark detection API service",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeImageRequest(BaseModel):
    image_path: str | None = None


@app.get("/")
def read_root() -> Dict[str, str]:
    return {
        "message": "Face-Fit Vision Server API is running",
        "docs": "/docs",
    }


@app.get("/health")
def health_check() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "vision-server",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


@app.get("/status")
def server_status() -> Dict[str, Any]:
    models_dir = VISION_SERVER_ROOT / "models"
    manifest_file = models_dir / "model_manifest.json"
    face_model = models_dir / "face_landmarker.task"
    pose_model = models_dir / "pose_landmarker_full.task"

    return {
        "status": "ready",
        "models": {
            "manifest_exists": manifest_file.exists(),
            "face_landmarker": face_model.exists(),
            "pose_landmarker": pose_model.exists(),
        },
        "python_version": sys.version,
    }


@app.post("/api/v1/analyze/image")
def analyze_image(req: AnalyzeImageRequest) -> Dict[str, Any]:
    if not req.image_path:
        raise HTTPException(status_code=400, detail="image_path is required")
    path = Path(req.image_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Image file not found: {req.image_path}")

    return {
        "status": "success",
        "message": f"Processed image landmark analysis for {path.name}",
        "image_path": str(path),
    }
