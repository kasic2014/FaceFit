# FaceFit 15단계 CV 시각 분석

- 확정일: 2026-08-03
- 배포 소스: 루트 `ai-server/analysis-server`
- HTTP DTO 버전: `1.0`
- 실행 방식: CPU, 단일 분석 executor, MediaPipe IMAGE mode 재사용
- 주의: 이 문서는 `docs/16_FaceFit_12단계_AI_HTTP계약.md`의 CV 503 설명만 대체한다. URI, multipart 필드, 성공 DTO와 공통 오류 envelope는 변경하지 않는다.

## 1. HTTP 계약

```http
POST /internal/v1/analyses/cv
Authorization: Bearer {FACEFIT_AI_SERVICE_TOKEN}
X-Request-Id: {UUID}
Content-Type: multipart/form-data
```

| 필드 | 형식 | 필수 |
|---|---|:---:|
| `answerId` | UUID | 예 |
| `media` | MP4 또는 WebM | 예 |

성공 응답은 기존 필드만 사용한다.

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "answerId": "00000000-0000-4000-8000-000000000002",
  "analysisType": "CV",
  "schemaVersion": "1.0",
  "modelVersion": "mediapipe:0.10.35:face-landmarker+pose-full",
  "gazeScore": 94.5,
  "postureScore": 100.0,
  "feedback": [
    "시선 점수는 눈동자가 아닌 머리 방향 기반 화면 정면 근사치입니다."
  ]
}
```

`gazeScore`는 실제 눈동자 시선 추적값이 아니다. 얼굴 랜드마크에서 계산한 머리 방향과 안정성을 화면 정면성의 근사값으로 표현한다.

## 2. 모델과 의존성

| 항목 | 버전·변형 | 공식 출처 | 무결성 |
|---|---|---|---|
| MediaPipe Python | `0.10.35` | `github.com/google-ai-edge/mediapipe` / PyPI | 버전 고정 |
| Face Landmarker | float16 latest bundle | `storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task` | SHA-256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff` |
| Pose Landmarker Full | full float16 latest bundle | `storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task` | SHA-256 `4eaa5eb7a98365221087693fcc286334cf0858e2eb6e15b506aa4a7ecdcec4ad` |
| PyAV | `>=12,<17` | PyPI | 영상 순차 디코딩 |
| OpenCV contrib headless | `5.0.0.93` | PyPI | MediaPipe 의존성의 GUI 배포판을 최종 이미지에서 교체 |

MediaPipe 소스와 OpenCV 4.5 이상은 Apache License 2.0이다. Google 공식 모델 번들은 공식 MediaPipe 문서가 제공하는 URL에서 빌드 시 내려받으며, 체크섬 불일치 시 이미지 빌드가 실패한다. 모델 파일의 별도 재배포 조건은 공식 모델 카드에서 명확히 확인되지 않았으므로 상용 배포 전 별도 라이선스 검토가 남아 있다. 런타임에는 모델 다운로드가 발생하지 않는다.

## 3. 처리 파이프라인

1. 기존 업로드 계층이 MIME, MP4/WebM 시그니처와 200MB 상한을 검사하면서 요청별 임시 디렉터리에 스트리밍 저장한다.
2. PyAV가 영상 스트림, FPS, 해상도, 실제 길이를 확인한다. 길이는 PyAV 마이크로초 값을 초로 나누어 계산하며 300초 초과는 거부한다.
3. 전체 영상을 한 번 순차 디코딩하되 균등 타임스탬프에서만 RGB 프레임을 선택한다. 기본값은 2 FPS, 최대 48프레임, 최소 유효 5프레임이다.
4. 긴 변의 해상도가 1280px를 넘으면 비율을 유지해 축소한다.
5. 프로세스당 Face Landmarker와 Pose Landmarker를 한 번 lazy 초기화하고 단일 executor에서 순차 재사용한다.
6. 얼굴 수·면적·중심, 머리 방향 근사값, 어깨 기울기·중심·머리 정렬·프레임 간 움직임을 계산한다.
7. 품질 게이트를 통과한 경우에만 0~100 점수와 공개 피드백을 반환한다.
8. 성공, 422, 500, 503, 504를 포함한 모든 종료 경로에서 임시 미디어를 삭제한다. 타임아웃 뒤 작업 스레드가 늦게 끝나면 완료 callback이 삭제한다.

모든 프레임에 랜드마크 추론을 반복하지 않으며, 한 요청의 추론 프레임 수는 환경변수 상한으로 고정된다. 원본 영상, 썸네일, 오버레이, 랜드마크 좌표는 결과나 로그에 저장하지 않는다.

## 4. 품질 게이트

다음 경우 낮은 점수를 만들어 성공시키지 않고 `422 MEDIA_ANALYSIS_FAILED`를 반환한다.

- 샘플 또는 유효 프레임이 5개 미만
- 유효 얼굴 프레임이 부족함
- 한 프레임이라도 얼굴이 2개 이상 검출됨
- 얼굴 면적이 화면의 2% 미만 또는 55% 초과인 프레임이 과반
- 얼굴 중심·머리 방향 또는 양쪽 어깨 지표가 전체 샘플의 절반 이상에서 확보되지 않음
- 빈 파일, 손상 파일, 지원하지 않는 코덱·컨테이너, 비정상 FPS·길이·해상도

모델 파일 누락·체크섬 불일치·초기화 실패는 `503 ANALYSIS_UNAVAILABLE`, 초기화 후 추론 실패는 `500 MODEL_ERROR`, executor 제한시간 초과는 재시도 가능한 `504 MODEL_TIMEOUT`이다.

## 5. 고정 MVP 산식

이 산식은 면접 합격 가능성이나 사람의 능력을 측정하는 검증된 심리·의학 척도가 아니라, 시연용 촬영 품질과 화면 정면성 피드백을 위한 기술적 휴리스틱이다.

선형 품질 함수 `q(x; good, bad)`는 `x <= good`이면 100, `x >= bad`이면 0, 그 사이는 선형 보간한다.

### Gaze 축(머리 방향 근사)

- yaw proxy: 코가 양쪽 볼 중심에서 벗어난 거리를 얼굴 너비로 정규화, `q(0.04, 0.22)`
- pitch proxy: 눈 중심과 턱 사이의 중립 코 위치에서 벗어난 거리를 얼굴 높이로 정규화, `q(0.04, 0.20)`
- roll: 양쪽 눈 선의 절대 기울기, `q(5°, 25°)`
- 얼굴 움직임: 연속 유효 프레임 얼굴 중심 이동량의 평균, `q(0.01, 0.08)`

프레임 정면성은 yaw·pitch·roll 품질의 산술평균이다.

```text
gazeScore = 0.85 × 평균 프레임 정면성 + 0.15 × 얼굴 움직임 안정성
```

### Posture 축(2D 상체 근사)

- 양쪽 어깨 기울기: `q(3°, 18°)`
- 어깨 중심의 화면 중앙 이탈: `q(0.05, 0.25)`
- 얼굴 중심과 어깨 중심의 수평 오프셋/어깨 너비: `q(0.08, 0.35)`
- 연속 유효 프레임 어깨 중심 이동량의 평균: `q(0.01, 0.10)`

```text
postureScore = 0.35 × 어깨 수평성
             + 0.25 × 화면 중앙 정렬
             + 0.20 × 머리-어깨 정렬
             + 0.20 × 상체 움직임 안정성
```

모든 점수는 유한값인지 확인하고 0~100으로 제한한 뒤 소수점 첫째 자리로 반올림한다. 동일한 입력·모델·환경변수에는 동일한 결과를 반환한다.

## 6. 피드백

피드백은 최대 5개이며 원본 좌표나 민감정보를 포함하지 않는다.

- 모든 성공 응답: 눈동자 시선이 아닌 머리 방향 근사임을 명시
- gaze 70 미만: 화면 정면과 머리 방향 안정성 안내
- 어깨 또는 머리-어깨 정렬 70 미만: 편안한 수평 정렬 안내
- 화면 중앙 정렬 70 미만: 카메라 위치 안내
- 움직임 안정성 70 미만: 큰 상체 움직임 완화 안내

## 7. 환경변수

| 변수 | 기본값 | 제한 |
|---|---:|---|
| `FACEFIT_CV_FACE_MODEL_PATH` | `{analysis-root}/models/face_landmarker.task` | 체크섬 일치 필수 |
| `FACEFIT_CV_POSE_MODEL_PATH` | `{analysis-root}/models/pose_landmarker_full.task` | 체크섬 일치 필수 |
| `FACEFIT_CV_SAMPLE_FPS` | `2` | 0 초과, 최대 10 |
| `FACEFIT_CV_MAX_SAMPLE_FRAMES` | `48` | 1~120 |
| `FACEFIT_CV_MIN_USABLE_FRAMES` | `5` | 최대 샘플 수 이하 |
| `FACEFIT_AI_MODEL_TIMEOUT_SECONDS` | `55` | Java Worker 60초 미만 |
| `FACEFIT_AI_MAX_DURATION_SECONDS` | `300` | 양수 |

Compose는 모델 경로를 `/app/models/...`로 명시한다. 경로가 빠지거나 모델이 변조되면 health endpoint는 살아 있어도 CV 요청은 503으로 안전하게 실패한다.

## 8. Docker 실행

```powershell
Copy-Item .env.example .env
# .env의 DB·Supabase·내부 서비스 토큰을 로컬 실제 값으로 교체한다.
docker compose --env-file .env -f infra/compose/compose.dev.yml config --quiet
docker compose --env-file .env -f infra/compose/compose.dev.yml up --build -d
docker compose --env-file .env -f infra/compose/compose.dev.yml ps
```

AI health는 `http://localhost:8001/health`, backend health는 `http://localhost:8080/actuator/health`에서 확인한다. backend 컨테이너는 `FACEFIT_AI_BASE_URL=http://analysis-server:8001`을 사용한다. 컨테이너 내부에서 `localhost:8001`을 사용하면 backend 자신을 가리키므로 안 된다.

종료할 때는 다음 명령으로 컨테이너와 전용 네트워크를 정리한다.

```powershell
docker compose --env-file .env -f infra/compose/compose.dev.yml down --remove-orphans
```

## 9. 테스트

```powershell
docker build --target test `
  -f infra/docker/analysis-server.Dockerfile `
  -t facefit-analysis-server:stage15-test .
docker run --rm facefit-analysis-server:stage15-test
```

테스트는 고정 관측값 산식과 실제 모델 추론을 분리한다.

- 고정 관측값: 정상, 낮은 점수, 얼굴 없음, 다중 얼굴, 거리 불량, 자세 부족, 결정성, 점수 범위
- 실제 PyAV: 합성 MP4의 순차 샘플링과 하드 프레임 상한
- 실제 MediaPipe: 체크섬 모델을 로드하고 합성 검은 프레임에서 얼굴 없음 검출
- HTTP: CV 200 및 422·500·503, 임시파일 삭제, VOICE·CONTENT 503, OpenAPI 저장본 일치
- Java: CV 성공 DTO 역직렬화·범위 위반 거부, 기존 Worker 저장과 리포트 평균 통합

## 10. 실제 영상 E2E와 성능

기존 저장소의 `SPK001_FRONT_SHOULDERS_STATIC_SMOKE_01.mp4`만 사용했다. README는 동의받은 정적 이미지를 반복한 파일이라고 명시하며 manifest에는 SHA-256, 720×960, 10 FPS, 30프레임, 3초, `synthetic_static_video=true`, smoke-test 전용임이 기록돼 있다. 새 사람 영상은 추가하지 않았다.

- 입력 크기: 379,240 bytes
- 샘플·유효 프레임: 5/5
- CPU cold 실행(모델 초기화 포함): 0.958~2.097초(3회 측정)
- 마지막 측정의 처리 속도: 3초 입력을 2.097초에 처리(약 1.43배 실시간)
- 마지막 측정의 프로세스 최대 RSS: 268,756 KiB(약 262.5 MiB)
- 최종 AI 런타임 이미지: 653,298,313 bytes, non-root `facefit`
- 14단계 기록 약 529.2MB 대비 Docker API 크기 약 124.1MB 증가(약 23.5%); 로컬 Docker CLI 가상 크기는 2.82GB
- 결과: gaze 94.5, posture 100.0, 피드백 1개
- 시계열 움직임 검증: 정적 반복 영상이므로 검증하지 않음

## 11. 실제 Supabase·실미디어 E2E 절차

이 검증에는 실제 `DB_URL`, DB 계정, Supabase JWT issuer, Supabase URL·secret key, Private Storage bucket과 내부 서비스 토큰이 필요하다. 값은 `.env` 또는 CI secret에만 두고 커밋하지 않는다.

1. 실제 값을 넣은 로컬 `.env`로 Compose를 기동하고 두 healthcheck가 healthy인지 확인한다.
2. 테스트 사용자 JWT로 이력서·채용공고·면접 세션을 만들고, 본인 소유 Private Storage에 영상·음성 스트림이 모두 있는 MP4 또는 WebM 답변을 업로드한다.
3. 면접 완료 후 CV Job이 `RUNNING → SUCCEEDED`인지, `interview_analysis_results`에 GAZE·POSTURE와 공개 피드백만 저장됐는지 확인한다.
4. 10개 답변을 완료해 리포트의 GAZE·POSTURE 산술평균과 HALF_UP 반올림을 확인한다.
5. 얼굴 없음·다중 얼굴·거리 불량·손상 영상은 기존 오류와 Job 실패 상태로 끝나며 정상 점수가 저장되지 않는지 확인한다.
6. 분석 중 AI 서버를 중단해 Java timeout·재시도·최종 실패 정책을 확인한다.
7. 로그에서 JWT, Supabase key, Storage URL, 원본 파일명·랜드마크가 노출되지 않았는지 검사하고 테스트 사용자와 미디어를 승인된 절차로 정리한다.

이번 작업 환경에는 실제 Supabase 인증정보가 없어 위 전체 흐름은 실행하지 않았다.

## 12. 알려진 한계

- gaze는 눈동자 추적이 아니라 머리 방향 근사다.
- 2D 어깨 기하만 사용하므로 척추·골반·깊이 기반 자세 평가가 아니다.
- 조명, 가림, 카메라 각도, 렌즈 왜곡, 얼굴·체형 다양성에 따른 편향 검증이 완료되지 않았다.
- 0~100 산식과 임계값은 시연용 고정 MVP 규칙이며 외부 연구로 타당화되지 않았다.
- 성별·나이·인종·감정·신원·건강·합격 가능성·채용 적합도를 추론하지 않는다.
- 실제 동적 MP4/WebM, 장시간 영상, 다양한 촬영 환경의 정확도·지연·메모리 벤치마크가 더 필요하다.
- MediaPipe native 경고는 모델 초기화 시 stderr에 출력될 수 있으나 토큰·미디어 경로·랜드마크는 애플리케이션 로그에 기록하지 않는다.
