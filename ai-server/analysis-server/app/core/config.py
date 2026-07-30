"""Filesystem paths used by the analysis server."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    """Paths managed by the analysis server."""

    root_dir: Path
    audio_input_dir: Path
    video_input_dir: Path
    output_dir: Path
    temp_dir: Path
    log_dir: Path

    def ensure_directories(self) -> None:
        """Create every managed directory when it does not already exist."""
        for directory in self.all_directories():
            directory.mkdir(parents=True, exist_ok=True)

    def all_directories(self) -> tuple[Path, ...]:
        """Return every managed directory in a stable order."""
        return (
            self.root_dir,
            self.audio_input_dir,
            self.video_input_dir,
            self.output_dir,
            self.temp_dir,
            self.log_dir,
        )


ANALYSIS_SERVER_ROOT = Path(__file__).resolve().parents[2]

APP_PATHS = AppPaths(
    root_dir=ANALYSIS_SERVER_ROOT,
    audio_input_dir=ANALYSIS_SERVER_ROOT / "data" / "input" / "audio",
    video_input_dir=ANALYSIS_SERVER_ROOT / "data" / "input" / "video",
    output_dir=ANALYSIS_SERVER_ROOT / "data" / "output",
    temp_dir=ANALYSIS_SERVER_ROOT / "data" / "temp",
    log_dir=ANALYSIS_SERVER_ROOT / "logs",
)
