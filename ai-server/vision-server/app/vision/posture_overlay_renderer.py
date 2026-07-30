"""Diagnostic overlay rendering for raw shoulder posture metrics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2

from app.vision.posture_raw_models import PostureRawConfiguration


class PostureOverlayError(RuntimeError):
    pass


def _pixel(
    point: dict[str, Any] | None,
    width: int,
    height: int,
) -> tuple[int, int] | None:
    if not point:
        return None
    return round(float(point["x"]) * width), round(float(point["y"]) * height)


def _label_point(
    frame: Any,
    point: tuple[int, int] | None,
    label: str,
    color: tuple[int, int, int],
    configuration: PostureRawConfiguration,
) -> None:
    if point is None:
        return
    cv2.circle(
        frame,
        point,
        configuration.overlay_point_radius_px,
        color,
        -1,
    )
    cv2.putText(
        frame,
        label,
        (point[0] + 8, point[1] - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        2,
        cv2.LINE_AA,
    )


def render_posture_overlay_frame(
    frame: Any,
    row: dict[str, Any],
    configuration: PostureRawConfiguration = PostureRawConfiguration(),
) -> Any:
    rendered = frame.copy()
    height, width = rendered.shape[:2]
    landmarks = row["landmarks"]
    raw = row["posture_raw"]
    left = _pixel(landmarks.get("left_shoulder"), width, height)
    right = _pixel(landmarks.get("right_shoulder"), width, height)
    nose = _pixel(landmarks.get("nose"), width, height)
    face_center = _pixel(landmarks.get("face_center"), width, height)
    shoulder_center = (
        (
            round(raw["shoulder_center_x"] * width),
            round(raw["shoulder_center_y"] * height),
        )
        if raw["shoulders_available"]
        else None
    )
    _label_point(rendered, left, "L_SHOULDER", (0, 255, 0), configuration)
    _label_point(rendered, right, "R_SHOULDER", (0, 200, 255), configuration)
    _label_point(rendered, shoulder_center, "SHOULDER_CENTER", (255, 0, 255), configuration)
    _label_point(rendered, nose, "NOSE", (0, 255, 255), configuration)
    _label_point(rendered, face_center, "FACE_CENTER", (255, 128, 0), configuration)
    thickness = configuration.overlay_line_thickness_px
    if left and right:
        cv2.line(rendered, left, right, (255, 255, 255), thickness)
    if shoulder_center and nose:
        cv2.line(rendered, shoulder_center, nose, (0, 255, 255), thickness)
    if shoulder_center and face_center:
        cv2.line(rendered, shoulder_center, face_center, (255, 128, 0), thickness)
    face_box = landmarks.get("face_bounding_box")
    if face_box:
        cv2.rectangle(
            rendered,
            (
                round(face_box["min_x"] * width),
                round(face_box["min_y"] * height),
            ),
            (
                round(face_box["max_x"] * width),
                round(face_box["max_y"] * height),
            ),
            (255, 128, 0),
            thickness,
        )

    event_types = row.get("posture_jump_candidates") or []
    event_labels = {
        "SHOULDER_TILT_JUMP_CANDIDATE": "TILT",
        "SHOULDER_CENTER_DISPLACEMENT_CANDIDATE": "CENTER",
        "SHOULDER_WIDTH_JUMP_CANDIDATE": "WIDTH",
        "NOSE_SHOULDER_OFFSET_X_JUMP_CANDIDATE": "NOSE_X",
        "NOSE_SHOULDER_OFFSET_Y_JUMP_CANDIDATE": "NOSE_Y",
        "FACE_SHOULDER_OFFSET_X_JUMP_CANDIDATE": "FACE_X",
        "FACE_SHOULDER_OFFSET_Y_JUMP_CANDIDATE": "FACE_Y",
    }

    def fmt(value: Any, digits: int = 3) -> str:
        return "null" if value is None else f"{float(value):.{digits}f}"

    values = [
        (
            f'{row["timestamp_ms"] / 1000:.3f}s target='
            f'{row["target_id"] or "NONE"} available={raw["available"]}'
        ),
        (
            f'tilt={fmt(raw["shoulder_tilt_deg"])} deg '
            f'height_diff={fmt(raw["shoulder_height_difference_norm"])}'
        ),
        (
            f'width={fmt(raw["shoulder_width_norm"])} '
            f'nose_offset=({fmt(raw["nose_shoulder_offset_x_norm"])}, '
            f'{fmt(raw["nose_shoulder_offset_y_norm"])})'
        ),
        (
            f'confidence={raw["confidence"]:.3f} '
            f'failure={raw["failure_reason"] or "NONE"}'
        ),
        (
            f'jump_candidates={len(event_types)} '
            f'{"|".join(event_labels.get(value, value) for value in event_types) if event_types else "NONE"}'
        ),
    ]
    panel_height = 30 + 27 * len(values)
    cv2.rectangle(rendered, (8, 8), (min(width - 8, 1180), panel_height), (0, 0, 0), -1)
    for index, text in enumerate(values):
        cv2.putText(
            rendered,
            text,
            (18, 35 + index * 27),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    return rendered


def write_posture_overlay(
    source: Path,
    output_path: Path,
    rows: list[dict[str, Any]],
    fps: float,
    *,
    representative_timestamps: set[int] | None = None,
    representative_directory: Path | None = None,
    configuration: PostureRawConfiguration = PostureRawConfiguration(),
) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise PostureOverlayError("Could not open source video")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        raise PostureOverlayError("Could not initialize overlay writer")
    wanted_representatives = representative_timestamps or set()
    if representative_directory is not None and wanted_representatives:
        representative_directory.mkdir(parents=True, exist_ok=True)
    current_index = 0
    written = 0
    representative_files: dict[str, str] = {}
    try:
        for row in rows:
            wanted = int(row["source_frame_index"])
            selected = None
            while current_index <= wanted:
                ok, decoded = capture.read()
                if not ok:
                    raise PostureOverlayError(
                        f"Could not decode source frame {wanted}"
                    )
                if current_index == wanted:
                    selected = decoded
                current_index += 1
            if selected is None:
                raise PostureOverlayError(f"Source frame {wanted} was not selected")
            rendered = render_posture_overlay_frame(
                selected,
                row,
                configuration,
            )
            writer.write(rendered)
            written += 1
            timestamp = int(row["timestamp_ms"])
            if (
                representative_directory is not None
                and timestamp in wanted_representatives
            ):
                name = f"frame_{row['sample_index']:03d}_{timestamp:06d}ms.png"
                path = representative_directory / name
                if not cv2.imwrite(str(path), rendered):
                    raise PostureOverlayError(
                        f"Could not write representative frame {name}"
                    )
                representative_files[str(timestamp)] = name
    finally:
        capture.release()
        writer.release()
    return {
        "width": width,
        "height": height,
        "fps": fps,
        "written_frame_count": written,
        "representative_files": representative_files,
    }
