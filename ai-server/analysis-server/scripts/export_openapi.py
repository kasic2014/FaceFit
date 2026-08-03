"""Export the deterministic FastAPI contract into ai-server/openapi."""

from __future__ import annotations

import json
import sys
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
AI_ROOT = SERVER_ROOT.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from app.main import app  # noqa: E402


def export_openapi(target: Path | None = None) -> Path:
    destination = target or AI_ROOT / "openapi" / "facefit-ai-openapi-v1.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        app.openapi(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(text + "\n", encoding="utf-8", newline="\n")
    temporary.replace(destination)
    return destination


if __name__ == "__main__":
    print(export_openapi())
