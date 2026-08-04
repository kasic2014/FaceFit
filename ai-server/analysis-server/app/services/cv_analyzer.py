"""Bounded CPU CV analysis using face and pose landmarks only.

The public ``gazeScore`` is deliberately a head-direction proxy.  This module
does not infer eye gaze, emotion, identity, demographics, or employability.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Protocol

import numpy as np

from app.services.analysis_contracts import (
    AnalyzerMediaFailure,
    AnalyzerModelError,
    AnalyzerPayloadTooLarge,
    AnalyzerUnavailable,
    CvAnalysisResult,
)


FACE_MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
POSE_MODEL_SHA256 = "4eaa5eb7a98365221087693fcc286334cf0858e2eb6e15b506aa4a7ecdcec4ad"
MODEL_VERSION = "mediapipe:0.10.35:face-landmarker+pose-full"
MIN_FACE_AREA = 0.02
MAX_FACE_AREA = 0.55


@dataclass(frozen=True)
class FrameObservation:
    face_count: int
    face_area: float | None = None
    face_center_x: float | None = None
    face_center_y: float | None = None
    yaw_proxy: float | None = None
    pitch_proxy: float | None = None
    roll_degrees: float | None = None
    shoulder_tilt_degrees: float | None = None
    shoulder_center_x: float | None = None
    shoulder_center_y: float | None = None
    head_shoulder_offset: float | None = None


class FrameObserver(Protocol):
    def observe(self, rgb_frame: np.ndarray) -> FrameObservation: ...

    def close(self) -> None: ...


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _point(landmarks, index: int) -> tuple[float, float] | None:
    if index >= len(landmarks):
        return None
    x = _finite(getattr(landmarks[index], "x", None))
    y = _finite(getattr(landmarks[index], "y", None))
    if x is None or y is None:
        return None
    return x, y


class MediaPipeFrameObserver:
    """One process-owned MediaPipe IMAGE-mode observer, reused sequentially."""

    def __init__(self, face_model_path: Path, pose_model_path: Path) -> None:
        for path, expected in (
            (face_model_path, FACE_MODEL_SHA256),
            (pose_model_path, POSE_MODEL_SHA256),
        ):
            try:
                if not path.is_file() or _sha256(path) != expected:
                    raise AnalyzerUnavailable
            except OSError as exc:
                raise AnalyzerUnavailable from exc

        try:
            import mediapipe as mp
            from mediapipe.tasks import python as tasks_python
            from mediapipe.tasks.python import vision

            face_options = vision.FaceLandmarkerOptions(
                base_options=tasks_python.BaseOptions(
                    model_asset_path=str(face_model_path)
                ),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=2,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
            pose_options = vision.PoseLandmarkerOptions(
                base_options=tasks_python.BaseOptions(
                    model_asset_path=str(pose_model_path)
                ),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=2,
                min_pose_detection_confidence=0.5,
                min_pose_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_segmentation_masks=False,
            )
            self._face = vision.FaceLandmarker.create_from_options(face_options)
            self._pose = vision.PoseLandmarker.create_from_options(pose_options)
            self._mp = mp
        except AnalyzerUnavailable:
            raise
        except (ModuleNotFoundError, ImportError, FileNotFoundError, OSError) as exc:
            raise AnalyzerUnavailable from exc
        except Exception as exc:
            raise AnalyzerUnavailable from exc

    def observe(self, rgb_frame: np.ndarray) -> FrameObservation:
        try:
            image = self._mp.Image(
                image_format=self._mp.ImageFormat.SRGB,
                data=np.ascontiguousarray(rgb_frame, dtype=np.uint8),
            )
            face_result = self._face.detect(image)
            pose_result = self._pose.detect(image)
        except Exception as exc:
            raise AnalyzerModelError from exc

        faces = list(getattr(face_result, "face_landmarks", ()) or ())
        if len(faces) != 1:
            return FrameObservation(face_count=len(faces))
        face = faces[0]
        coordinates = [
            point
            for point in (_point(face, index) for index in range(len(face)))
            if point is not None
        ]
        if not coordinates:
            return FrameObservation(face_count=1)
        xs, ys = zip(*coordinates)
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if width <= 0 or height <= 0:
            return FrameObservation(face_count=1)
        center_x = (min(xs) + max(xs)) / 2.0
        center_y = (min(ys) + max(ys)) / 2.0

        nose = _point(face, 1)
        left_eye = _point(face, 33)
        right_eye = _point(face, 263)
        left_cheek = _point(face, 234)
        right_cheek = _point(face, 454)
        chin = _point(face, 152)
        head_metrics = (nose, left_eye, right_eye, left_cheek, right_cheek, chin)
        yaw = pitch = roll = None
        if all(point is not None for point in head_metrics):
            eye_mid_y = (left_eye[1] + right_eye[1]) / 2.0
            cheek_mid_x = (left_cheek[0] + right_cheek[0]) / 2.0
            yaw = abs(nose[0] - cheek_mid_x) / width
            neutral_nose_y = eye_mid_y + 0.45 * (chin[1] - eye_mid_y)
            pitch = abs(nose[1] - neutral_nose_y) / height
            roll = abs(math.degrees(math.atan2(
                right_eye[1] - left_eye[1],
                right_eye[0] - left_eye[0],
            )))

        poses = list(getattr(pose_result, "pose_landmarks", ()) or ())
        shoulder_tilt = shoulder_x = shoulder_y = head_offset = None
        if len(poses) == 1:
            left_shoulder = _point(poses[0], 11)
            right_shoulder = _point(poses[0], 12)
            if left_shoulder is not None and right_shoulder is not None:
                dx = right_shoulder[0] - left_shoulder[0]
                dy = right_shoulder[1] - left_shoulder[1]
                shoulder_width = math.hypot(dx, dy)
                if shoulder_width >= 0.05:
                    shoulder_tilt = abs(math.degrees(math.atan2(dy, abs(dx))))
                    shoulder_x = (left_shoulder[0] + right_shoulder[0]) / 2.0
                    shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2.0
                    head_offset = abs(center_x - shoulder_x) / shoulder_width

        return FrameObservation(
            face_count=1,
            face_area=width * height,
            face_center_x=center_x,
            face_center_y=center_y,
            yaw_proxy=yaw,
            pitch_proxy=pitch,
            roll_degrees=roll,
            shoulder_tilt_degrees=shoulder_tilt,
            shoulder_center_x=shoulder_x,
            shoulder_center_y=shoulder_y,
            head_shoulder_offset=head_offset,
        )

    def close(self) -> None:
        for landmarker in (getattr(self, "_face", None), getattr(self, "_pose", None)):
            if landmarker is not None:
                try:
                    landmarker.close()
                except Exception:
                    pass


def sample_video_frames(
    media_path: Path,
    *,
    sample_fps: float,
    max_frames: int,
    min_frames: int,
    max_duration_seconds: int,
) -> Iterable[np.ndarray]:
    """Sequentially decode once while bounding expensive inference frames."""
    try:
        import av
    except (ModuleNotFoundError, ImportError) as exc:
        raise AnalyzerUnavailable from exc

    try:
        with av.open(str(media_path)) as container:
            streams = [stream for stream in container.streams if stream.type == "video"]
            if len(streams) != 1 or container.duration is None:
                raise AnalyzerMediaFailure
            stream = streams[0]
            duration = float(container.duration / av.time_base)
            fps = _finite(stream.average_rate)
            if (
                not math.isfinite(duration)
                or duration <= 0
                or fps is None
                or fps <= 0
                or stream.width <= 0
                or stream.height <= 0
            ):
                raise AnalyzerMediaFailure
            if duration > max_duration_seconds:
                raise AnalyzerPayloadTooLarge

            target_count = min(
                max_frames,
                max(min_frames, int(math.ceil(duration * sample_fps))),
            )
            end = max(0.0, duration - min(0.05, 0.5 / fps))
            targets = np.linspace(0.0, end, target_count).tolist()
            target_index = 0
            for frame in container.decode(stream):
                timestamp = _finite(frame.time)
                if timestamp is None:
                    continue
                if target_index >= target_count:
                    break
                if timestamp + (0.5 / fps) < targets[target_index]:
                    continue
                while (
                    target_index + 1 < target_count
                    and targets[target_index + 1] <= timestamp + (0.5 / fps)
                ):
                    target_index += 1
                width, height = int(frame.width), int(frame.height)
                maximum = max(width, height)
                if maximum > 1280:
                    scale = 1280.0 / maximum
                    frame = frame.reformat(
                        width=max(1, int(round(width * scale))),
                        height=max(1, int(round(height * scale))),
                        format="rgb24",
                    )
                yield frame.to_ndarray(format="rgb24")
                target_index += 1
    except (AnalyzerMediaFailure, AnalyzerPayloadTooLarge, AnalyzerUnavailable):
        raise
    except Exception as exc:
        raise AnalyzerMediaFailure from exc


def _quality(value: float, good: float, bad: float) -> float:
    if not math.isfinite(value):
        return 0.0
    if value <= good:
        return 100.0
    if value >= bad:
        return 0.0
    return 100.0 * (bad - value) / (bad - good)


def score_observations(
    observations: Iterable[FrameObservation],
    *,
    min_usable_frames: int,
    model_version: str = MODEL_VERSION,
) -> CvAnalysisResult:
    frames = tuple(observations)
    if len(frames) < min_usable_frames:
        raise AnalyzerMediaFailure
    if any(frame.face_count > 1 for frame in frames):
        raise AnalyzerMediaFailure

    single_faces = [frame for frame in frames if frame.face_count == 1]
    if len(single_faces) < min_usable_frames:
        raise AnalyzerMediaFailure
    sized = [frame for frame in single_faces if frame.face_area is not None]
    if len(sized) < min_usable_frames:
        raise AnalyzerMediaFailure
    out_of_range = [
        frame for frame in sized
        if frame.face_area < MIN_FACE_AREA or frame.face_area > MAX_FACE_AREA
    ]
    if len(out_of_range) > len(sized) / 2:
        raise AnalyzerMediaFailure

    required = (
        "face_center_x", "face_center_y", "yaw_proxy", "pitch_proxy",
        "roll_degrees", "shoulder_tilt_degrees", "shoulder_center_x",
        "shoulder_center_y", "head_shoulder_offset",
    )
    usable = [
        frame for frame in sized
        if MIN_FACE_AREA <= frame.face_area <= MAX_FACE_AREA
        and all(_finite(getattr(frame, field)) is not None for field in required)
    ]
    if len(usable) < min_usable_frames or len(usable) < math.ceil(len(frames) * 0.5):
        raise AnalyzerMediaFailure

    facing = [
        (
            _quality(frame.yaw_proxy, 0.04, 0.22)
            + _quality(frame.pitch_proxy, 0.04, 0.20)
            + _quality(frame.roll_degrees, 5.0, 25.0)
        ) / 3.0
        for frame in usable
    ]
    face_moves = [
        math.hypot(current.face_center_x - previous.face_center_x,
                   current.face_center_y - previous.face_center_y)
        for previous, current in zip(usable, usable[1:])
    ]
    face_stability = _quality(
        sum(face_moves) / len(face_moves) if face_moves else 0.0,
        0.01,
        0.08,
    )
    gaze_score = 0.85 * (sum(facing) / len(facing)) + 0.15 * face_stability

    tilt = sum(_quality(frame.shoulder_tilt_degrees, 3.0, 18.0) for frame in usable) / len(usable)
    center = sum(_quality(abs(frame.shoulder_center_x - 0.5), 0.05, 0.25) for frame in usable) / len(usable)
    alignment = sum(_quality(frame.head_shoulder_offset, 0.08, 0.35) for frame in usable) / len(usable)
    shoulder_moves = [
        math.hypot(current.shoulder_center_x - previous.shoulder_center_x,
                   current.shoulder_center_y - previous.shoulder_center_y)
        for previous, current in zip(usable, usable[1:])
    ]
    movement = _quality(
        sum(shoulder_moves) / len(shoulder_moves) if shoulder_moves else 0.0,
        0.01,
        0.10,
    )
    posture_score = 0.35 * tilt + 0.25 * center + 0.20 * alignment + 0.20 * movement

    feedback = ["시선 점수는 눈동자가 아닌 머리 방향 기반 화면 정면 근사치입니다."]
    if gaze_score < 70:
        feedback.append("답변 중 얼굴과 머리 방향을 화면 정면에 더 안정적으로 유지해 보세요.")
    if tilt < 70 or alignment < 70:
        feedback.append("양쪽 어깨의 기울기와 머리-어깨 정렬을 편안하게 맞춰 보세요.")
    if center < 70:
        feedback.append("상체가 화면 중앙에 오도록 카메라 위치를 조정해 보세요.")
    if movement < 70:
        feedback.append("답변 중 상체의 큰 움직임을 조금 줄여 보세요.")

    return CvAnalysisResult(
        model_version=model_version,
        gaze_score=round(max(0.0, min(100.0, gaze_score)), 1),
        posture_score=round(max(0.0, min(100.0, posture_score)), 1),
        feedback=tuple(feedback[:5]),
    )


class MediaPipeCvAnalyzer:
    def __init__(
        self,
        *,
        face_model_path: Path,
        pose_model_path: Path,
        sample_fps: float,
        max_sample_frames: int,
        min_usable_frames: int,
        max_duration_seconds: int,
        observer: FrameObserver | None = None,
    ) -> None:
        if min_usable_frames > max_sample_frames:
            raise ValueError("CV minimum usable frames cannot exceed the sample cap")
        self._face_model_path = face_model_path
        self._pose_model_path = pose_model_path
        self._sample_fps = sample_fps
        self._max_sample_frames = max_sample_frames
        self._min_usable_frames = min_usable_frames
        self._max_duration_seconds = max_duration_seconds
        self._observer = observer

    def _require_observer(self) -> FrameObserver:
        if self._observer is None:
            self._observer = MediaPipeFrameObserver(
                self._face_model_path,
                self._pose_model_path,
            )
        return self._observer

    def analyze(self, media_path: Path) -> CvAnalysisResult:
        observer = self._require_observer()
        observations = (
            observer.observe(frame)
            for frame in sample_video_frames(
                media_path,
                sample_fps=self._sample_fps,
                max_frames=self._max_sample_frames,
                min_frames=self._min_usable_frames,
                max_duration_seconds=self._max_duration_seconds,
            )
        )
        try:
            return score_observations(
                observations,
                min_usable_frames=self._min_usable_frames,
            )
        except (
            AnalyzerMediaFailure,
            AnalyzerModelError,
            AnalyzerPayloadTooLarge,
            AnalyzerUnavailable,
        ):
            raise
        except Exception as exc:
            raise AnalyzerModelError from exc

    def close(self) -> None:
        if self._observer is not None:
            self._observer.close()
