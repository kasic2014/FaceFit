# Face-Fit vision-server

## VIDEO-mode landmark pipeline

The video pipeline performs technical Face/Pose landmark detection only. It
does not calculate gaze, head pose, yaw/pitch/roll, shoulder angle, movement
scores, emotion, confidence, or posture quality.

Supported local video extensions are MP4, MOV, M4V, AVI, MKV, and WEBM.
Extensions are allow-listed, but every input must also open and decode through
OpenCV with positive width, height, and FPS metadata.

Create the deterministic static-image smoke video:

```powershell
.\.venv\Scripts\python.exe .\scripts\create_static_image_smoke_video.py `
  --input .\data\input\images\SPK001_FRONT_SHOULDERS_01.jpg
```

Analyze it at the default 5 FPS:

```powershell
.\.venv\Scripts\python.exe .\scripts\analyze_video.py `
  --input .\data\input\videos\generated\SPK001_FRONT_SHOULDERS_STATIC_SMOKE_01.mp4 `
  --analysis-fps 5
```

Optional flags are `--output-root`, `--overwrite`, `--no-overlay`,
`--require-overlay`, and `--save-all-sampled-frames`. Analysis FPS must be
between 1 and 15. The effective FPS never exceeds the source FPS.

Each sampled frame calls Face and Pose `detect_for_video()` exactly once with a
strictly increasing integer timestamp. One Face model and one Pose model are
created per video, reused for all sampled frames, and closed afterward.

Outputs:

```text
data/output/videos/<safe_video_id>/
|-- analysis.json
|-- frames.jsonl
|-- combined_overlay.mp4
`-- sampled_frames/
```

`frames.jsonl` retains the complete MediaPipe landmark arrays for technical
verification. Service availability is based only on nose, left shoulder, and
right shoulder. Left and right ears are optional. Chin, wrist, pelvis, knee,
ankle, and lower-body landmarks are not service requirements.

The generated smoke video repeats one consented static image for three seconds.
It validates decoding, deterministic sampling, VIDEO-mode inference, result
writing, and overlay encoding. It is explicitly not evidence for real motion,
tracking accuracy, temporal smoothing, gaze change, or posture change.

`vision-server`는 Face-Fit의 MediaPipe 기반 얼굴·자세 영상 분석을 위한 독립
Python 실행 환경이다. 현재 2단계는 공식 모델을 안전하게 다운로드해 SHA-256
기준선으로 고정하고, IMAGE 모드 생성·종료까지 검증한다.

## analysis-server와 분리한 이유

기존 `analysis-server`에는 faster-whisper, GPU STT, speech metrics, prosody
의존성이 고정되어 있다. MediaPipe가 요구하는 NumPy와 OpenCV 계열 패키지가 그
환경을 변경하지 않도록 별도의 `.venv`를 사용한다.

## Python 3.12 가상환경

프로젝트 루트에서 실행한다.

```powershell
py -3.12 -m venv ai-server\vision-server\.venv
```

Windows Python Launcher가 설치된 Python을 찾지 못하지만 Python 3.12.10의
실제 경로가 확인된 현재 장비에서는 같은 버전을 직접 지정했다.

```powershell
& 'C:\Users\SMHRD\AppData\Local\Programs\Python\Python312\python.exe' -m venv ai-server\vision-server\.venv
```

다른 Python 버전으로 대체하지 않는다. 이후 모든 명령은 새 환경의 실행 파일을
사용한다.

## 패키지 설치

```powershell
.\ai-server\vision-server\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\ai-server\vision-server\.venv\Scripts\python.exe -m pip install -r .\ai-server\vision-server\requirements.txt
```

MediaPipe 0.10.35가 `opencv-contrib-python` 5.0.0.93을 의존성으로 설치하므로
OpenCV 패키지를 별도로 중복 설치하지 않는다.

## 환경 점검

`vision-server`에서 실행한다.

```powershell
cd C:\Users\SMHRD\Documents\face-fit\ai-server\vision-server
.\.venv\Scripts\python.exe .\scripts\check_vision_environment.py
```

점검기는 운영체제, 아키텍처, Python·pip·가상환경, MediaPipe·NumPy·OpenCV
import와 버전, Tasks API, 디렉터리 권한, `pip check`를 검사하고
`environment_report.json`을 원자적으로 저장한다. 종료 코드는 성공 `0`, 환경
실패 `1`, 잘못된 CLI 사용 `2`이다.

## 공식 모델 설정

Google 공식 MediaPipe 저장소에서 Face Landmarker `float16_latest`와 Pose
Landmarker Full `full_float16_latest`만 사용한다. Lite와 Heavy 모델은 이
기준선에 포함하지 않는다.

```powershell
cd C:\Users\SMHRD\Documents\face-fit\ai-server\vision-server
.\.venv\Scripts\python.exe .\scripts\setup_mediapipe_models.py
```

다운로드는 HTTPS와 `storage.googleapis.com`만 허용하고, 임시 파일의 형식·크기와
SHA-256을 확인한 뒤 원자적으로 배치한다. 기존 파일은
`models/model_manifest.json`과 일치할 때 건너뛴다. 검증 모델을 의도적으로
교체할 때만 `--overwrite-models`를 사용한다.

## 모델 로딩 점검

```powershell
.\.venv\Scripts\python.exe .\scripts\check_mediapipe_model_loading.py
```

Face와 Pose Full 모델을 각각 한 번 IMAGE 모드로 생성하고 즉시 `close()`한다.
`detect()`, 영상 추론, 웹캠 처리는 호출하지 않는다. 결과는 strict JSON인
`model_loading_report.json`에 원자적으로 기록한다.

## 정적 이미지 분석

로컬 이미지 한 장에서 Face와 Pose 랜드마크를 검출한다.

```powershell
cd C:\Users\SMHRD\Documents\face-fit\ai-server\vision-server
.\.venv\Scripts\python.exe .\scripts\analyze_static_image.py `
  --input .\data\input\images\<이미지파일>
```

선택 옵션:

```powershell
--output-root .\data\output\static_images
--overwrite
--no-overlays
```

지원 형식은 JPG, JPEG, PNG, WEBP, BMP이다. 확장자와 OpenCV 디코딩을 모두
검사한다. 입력은 로컬에서만 처리하며 외부로 업로드하거나 원본 파일을 수정하지
않는다.

기본 출력 구조:

```text
data/output/static_images/<safe_image_id>/
├─ analysis.json
├─ face_overlay.png
├─ pose_overlay.png
└─ combined_overlay.png
```

`analysis.json`에는 입력 메타데이터와 SHA-256, 환경·모델 기준선, Face/Pose
landmark와 bounding box, 실행 시간, 출력 경로가 strict JSON으로 저장된다.
MediaPipe의 normalized 좌표는 그대로 보존하며 오버레이 픽셀 좌표만 이미지
범위로 제한한다.

오버레이는 개발 검증용이다. 색상에는 평가 의미가 없고 감정이나 자세 상태를
표시하지 않는다. 얼굴 또는 자세가 검출되지 않는 것은 정상 결과일 수 있으며
CLI 종료 코드도 0이다. `--no-overlays`를 사용하면 JSON만 생성한다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Real-motion temporal landmark validation

Run the existing MediaPipe VIDEO pipeline at 5 FPS, then validate normalized
face/shoulder landmark availability and frame-to-frame stability:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_motion_video_landmarks.py `
  --input .\data\input\videos\motion\SPK001_FACE_SHOULDERS_MOTION_01.mp4 `
  --analysis-fps 5
```

Use `--reuse-video-analysis` only when a matching source SHA-256 and analysis
FPS result already exists. Outputs are written atomically below
`data/output/motion_validation/<safe_video_id>/`. `--overwrite` replaces only
that exact validation directory.

This is a pipeline smoke validation. Jump candidates use a robust median/MAD
diagnostic and do not automatically indicate an error. Missing landmarks are
not interpolated. Head pose, iris, gaze direction, shoulder tilt, and posture
scoring are deliberately outside this stage.

## Session-local single-target tracking

Stage 6 runs a separate multi-candidate Face/Pose pass without changing the
existing one-person VIDEO analysis or temporal-validation schemas:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_video_target_tracking.py `
  --input .\data\input\videos\motion\SPK001_FACE_SHOULDERS_MOTION_01.mp4 `
  --analysis-fps 5
```

Results are written atomically below
`data/output/target_tracking_validation/<safe_video_id>/`. The tracker creates
a session-local `TARGET_001` label, combines normalized face/pose geometry,
uses time-based loss hysteresis, and does not switch when a match is ambiguous.
This label is not biometric identity. If MediaPipe exposes only one candidate
in the validation video, the report records that limitation instead of
claiming that real multi-candidate ambiguity was observed.

## Raw approximate head pose

Stage 7 derives raw yaw, pitch, and roll for the selected `TARGET_001` face:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_video_head_pose.py `
  --input .\data\input\videos\motion\SPK001_FACE_SHOULDERS_MOTION_01.mp4 `
  --analysis-fps 5
```

The estimator uses six Face Landmarker points, SQPnP plus iterative refinement,
and approximate intrinsics (`focal length = frame width`, principal point at
the frame center, zero distortion). No camera calibration is available, so
these raw values support relative direction/change checks under the same
setup, not guaranteed physical-angle accuracy. Missing frames remain null;
smoothing and evaluation scoring are not applied.

Signs are consistent across JSON, CSV, overlay, and reports: yaw left is
negative/right positive, pitch down is negative/up positive, and roll left
tilt is negative/right tilt positive.

## Raw 2D shoulder posture metrics

Stage 8 calculates limited raw shoulder and head-to-shoulder alignment proxies
for the selected session-local `TARGET_001`:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_video_posture_raw.py `
  --input .\data\input\videos\motion\SPK001_FACE_SHOULDERS_MOTION_01.mp4 `
  --analysis-fps 5
```

Only MediaPipe Pose nose (0), anatomical left shoulder (11), anatomical right
shoulder (12), and the geometrically matched face bounding-box center are used.
Elbows, wrists, hands, hips, pelvis, lower-body, and full-body landmarks are
not inputs. Results are written atomically below
`data/output/posture_raw_validation/<safe_video_id>/`.

Coordinates are image-normalized: x grows screen-right and y grows downward.
The shoulder tilt and height-difference sign is positive when the subject's
anatomical right shoulder is lower, and negative when the anatomical left
shoulder is lower. Horizontal face/nose offsets are screen-left negative and
screen-right positive. The raw metrics include shoulder center, width, tilt,
height difference, nose/face alignment, and timestamp-based changes. Missing
values remain null; smoothing and automatic baseline correction are disabled.

Configuration is centralized in `PostureRawConfiguration`. The default minimum
normalized shoulder width is 0.02 to reject collapsed points, the accepted
coordinate margin is 0.10 for small MediaPipe boundary excursions, confidence
uses explicit target/landmark/range/width/temporal quality weights, and change
candidates use `median + 6 × MAD` with metric-specific minimum thresholds.
Candidates are diagnostics for overlay review, not tracking failures or posture
judgments.

Confidence is calculation quality, not posture quality. These 2D proxies do not
measure the spine, pelvis, calibrated depth, or full-body posture, and they are
not converted into posture, attitude, confidence, focus, anxiety, or interview
scores.

## Session neutral baseline and relative raw features

Stage 9 keeps raw values, the session-local baseline, and relative values as
separate data. It selects stable candidate frames independently for Head Pose,
shoulders, nose alignment, and face alignment, then uses median aggregation
with MAD outlier filtering:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_neutral_baseline_model.py `
  --input .\data\input\videos\motion\SPK001_FACE_SHOULDERS_MOTION_01.mp4
```

The optional smoke command links the protected Stage 6, 7, and 8 JSONL files
by exact `timestamp_ms + TARGET_001`. It derives Head Pose angular velocity
from consecutive unsmoothed raw angles and real timestamp differences. Missing
frames reset the velocity chain.

Outputs are written atomically below
`data/output/neutral_baseline_smoke/<safe_video_id>/`:

```text
baseline.json
relative_features.jsonl
validation_report.json
validation_report.md
```

Each relative metric retains `raw_value`, `baseline_value`, and
`relative_value`, where the relative value is `raw - baseline`. Unavailable or
non-finite inputs produce `null` plus an explicit failure reason; `0.0` is
never used as a failure substitute. Face-alignment baseline availability is
independent from shoulder and nose baselines.

The first two seconds of the current movement video are used only as a
technical collection smoke test. They are not labeled neutral ground truth.
The baseline is a reference for the same user, camera, and session setup, not
an absolute normal or correct posture. `quality_score` measures collection
quality only and is never a posture, interview, confidence, focus, or anxiety
score. Stage 9 adds no smoothing, calibration, scoring, or evaluation
thresholds.

## Answer-interval relative feature aggregation

Stage 10 aggregates frame-level relative features into injected time
intervals. The core calculator is independent of JSONL and uses this boundary
rule:

```text
start_timestamp_ms <= timestamp_ms < end_timestamp_ms
```

Interval ends are exclusive. Duplicate IDs and overlapping intervals are
rejected by default. Head Pose, shoulder, nose alignment, and face alignment
availability remain independent.

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_interval_aggregation.py `
  --input .\data\input\videos\motion\SPK001_FACE_SHOULDERS_MOTION_01.mp4
```

Custom interval definitions can be supplied with `--intervals-json`. The
default smoke run uses four `OTHER` intervals covering the protected movement
video; they are not recorded interview answers.

Each finite relative metric provides min, max, mean, median, MAD, population
standard deviation, linearly interpolated p05/p25/p75/p95, and separate
absolute statistics. Empty metrics remain null with an explicit failure
reason. Existing Stage 8 timestamp-based posture displacement, delta, and
velocity values are reused without recalculation. Head angular velocity is not
present upstream, so it remains null instead of being inferred across missing
frames.

Longest missing duration uses real timestamps. A leading run starts at the
interval boundary, a trailing run ends at the exclusive boundary, and a
middle run ends at the next available timestamp. Diagnostic Stage 7/8 jump
events are linked with the same interval boundary rule and are not converted
into evaluations.

Outputs are written atomically below
`data/output/interval_aggregation_validation/<safe_video_id>/`:

```text
validation_report.json
validation_report.md
interval_definitions.json
interval_aggregates.jsonl
```

The interval quality value describes data availability, timestamps, target
continuity, and duplicates only. Aggregates are not posture or interview
evaluations. No evidence threshold, grade, feedback, behavioral inference,
smoothing, or camera calibration is applied.

## Evidence and scoring contract fixtures

Stage 11 models a versioned evidence-to-metric-to-threshold-to-result chain
without adding real research values or production scoring. The central metric
registry resolves existing Stage 10 paths and supplies their units. Evidence
sources, extracted records, metric mappings, evidence profiles, threshold
profiles, data-quality gates, score provenance, and unresolved conflicts are
kept as separate immutable contracts.

All files in `config/evidence/fixtures/` are synthetic contract-test data with
`TEST_FIXTURE` status. `PRODUCTION_MODE` rejects them. Fixture results use only
the explicit `test_fixture_score` field and `SCORED_TEST_FIXTURE` status; they
are not posture scores, interview scores, grades, confidence values, or user
feedback.

Run the protected Stage 10 connection smoke with:

```powershell
.\.venv\Scripts\python.exe .\scripts\validate_evidence_scoring_contract.py
```

The command reads the existing `interval_aggregates.jsonl`, resolves the three
fixture-rule metrics, applies availability and quality gates, and verifies the
full source-to-result provenance chain. It does not recompute or modify Stages
5-10. Outputs are written atomically below
`data/output/evidence_scoring_contract_validation/<safe_video_id>/`.

이 단계의 모든 수치와 band는 합성 테스트 fixture입니다. 실제 논문 근거,
운영 threshold, 사용자 자세 평가, 면접 점수 또는 피드백으로 사용할 수
없습니다. 실제 적용 전에는 출처 원문 검토, 측정 환경 적합성 검토, 전문가
승인, 별도 데이터셋 검증이 필요합니다.

테스트는 모델을 다운로드하거나 로드하지 않는다.

## 현재 구현 범위

- MediaPipe 설치와 패키지 import 검증
- Face/Pose Landmarker를 포함한 Tasks API 존재 검증
- 입력·출력·모델 디렉터리와 경로 설정 준비
- strict JSON 환경 보고서와 CLI 종료 코드
- 공식 Face Landmarker 및 Pose Landmarker Full 모델의 안전한 다운로드
- 모델 manifest, 파일 크기 및 SHA-256 기준선
- IMAGE 모드 landmarker 생성과 명시적 리소스 종료 검증
- 정적 이미지 입력 검증과 Face/Pose landmark 검출
- landmark strict JSON 직렬화와 개발 검증용 PNG 오버레이
- 정상적인 얼굴·자세 미검출 결과 처리

## 아직 구현하지 않은 기능

- 영상 분석
- 시선·자세 분석
- FastAPI
- 실시간 웹캠 처리

## 모델 관리 주의사항

모델 파일을 Git에 포함할지는 아직 결정하지 않았다. 모델 라이선스는 확인되지
않은 내용을 단정하지 않고 별도로 검토한다. 모델이나 `latest` 기준선을 바꾸면
manifest의 파일 크기·SHA-256과 Face/Pose 로딩 결과를 모두 다시 검증해야 한다.

## 다음 단계

동의받은 고정 정적 이미지 데이터셋에서 검출 품질과 실패 사례를 확인한다. 현재는
랜드마크 검출까지만 구현했으며 시선 방향, Head Pose, 자세 각도·점수는 아직
구현하지 않았다. 이후 단계에서도 영상·웹캠 처리는 별도 범위로 관리한다.
