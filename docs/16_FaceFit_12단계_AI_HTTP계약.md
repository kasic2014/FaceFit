# FaceFit 12단계 AI HTTP 계약

- 확정일: 2026-07-31
- HTTP DTO schemaVersion: `1.0`
- 내부 연동 대상: Spring Boot Worker
- 사용자 브라우저 직접 호출: 금지

## 1. 단일 Python 배포 소스

운영 변경의 단일 기준은 저장소 루트의 `ai-server/`다.

`FaceFit/ai-server/`는 이전 사본 또는 참고 자료로 취급한다. 이번 단계에서
삭제·덮어쓰기·자동 동기화를 수행하지 않았다. 작업 전 파일 비교 결과는 다음과
같다.

| 구분 | 파일 수 |
|---|---:|
| 루트 `ai-server/` | 414 |
| `FaceFit/ai-server/` 사본 | 380 |
| 루트에만 존재 | 34 |
| 사본에만 존재 | 0 |

루트에만 FastAPI `main.py`, 환경설정 예시, README와 배포용 골격이 존재한다.
양쪽에 공통으로 있는 연구·분석 모듈의 파일 내용까지 자동 동기화하지 않는다.

## 2. 실제 Method와 URI

HTTP 진입점은 `ai-server/analysis-server/app/main.py`다.

| Method | URI | 현재 동작 |
|---|---|---|
| GET | `/health` | 기존 호환 공개 health |
| POST | `/internal/v1/analyses/stt` | Whisper STT 성공 경로 |
| POST | `/internal/v1/analyses/cv` | 200 `CvSuccessResponse` 또는 기존 오류 envelope |
<!-- Stage 15 CV behavior and scoring are authoritative in docs/18_FaceFit_15단계_CV_분석.md. -->
| POST | `/internal/v1/analyses/voice` | 503 `ANALYSIS_UNAVAILABLE` |
| POST | `/internal/v1/analyses/content` | 503 `ANALYSIS_UNAVAILABLE` |

CV·VOICE·CONTENT는 향후 계약 URI를 미리 확정한 것이며 현재 성공 가능한
분석이라고 문서화하지 않는다.

## 3. 인증 계약

분석 endpoint는 다음 헤더를 요구한다.

```http
Authorization: Bearer {AI_SERVICE_TOKEN}
```

서버 환경변수는 `FACEFIT_AI_SERVICE_TOKEN`이다. 실제 토큰은 Secret Manager
또는 배포 환경에서만 주입한다.

- 누락 또는 불일치: `401 UNAUTHORIZED`
- 서버 토큰 미설정: `503 ANALYSIS_UNAVAILABLE`
- 비교: Python `secrets.compare_digest`
- Spring 사용자 JWT, Supabase JWT·Service Role Key, Worker claim token 전달 금지
- 토큰의 전체 또는 일부 로그 출력 금지
- `/health`는 기존 배포 점검 호환성을 위해 인증하지 않는다.

## 4. 공통 요청 헤더

```http
X-Request-Id: {UUID}
```

- 누락 또는 UUID 형식 오류: `400 INVALID_REQUEST`
- 성공·오류 응답에 동일한 `requestId` 반환
- Worker claim token을 requestId로 사용하지 않음
- 개인정보·Storage 경로를 requestId에 포함하지 않음
- 현재 Python 서버는 외부 멱등성 저장소와 `Idempotency-Key`를 지원하지 않음

## 5. 공통 성공 응답

실제 성공 가능한 분석은 다음 필드를 공통으로 반환한다.

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "answerId": "00000000-0000-4000-8000-000000000002",
  "analysisType": "STT",
  "schemaVersion": "1.0",
  "modelVersion": "faster-whisper:{packageVersion}:base"
}
```

- `answerId`는 요청값을 그대로 사용한다.
- `analysisType`은 endpoint에 고정한다.
- `schemaVersion`은 HTTP DTO 버전이다.
- `modelVersion`은 실행한 분석기의 실제 설정값에서 만든다.
- 알 수 없는 버전을 `latest`로 대체하지 않는다.

## 6. 공통 오류 envelope

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "code": "ANALYSIS_UNAVAILABLE",
  "message": "The requested analysis is not available.",
  "retryable": false
}
```

| HTTP | code | retryable |
|---:|---|:---:|
| 400 | `INVALID_REQUEST` | false |
| 401 | `UNAUTHORIZED` | false |
| 413 | `PAYLOAD_TOO_LARGE` | false |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | false |
| 422 | `MEDIA_ANALYSIS_FAILED` | false |
| 500 | `MODEL_ERROR` | false |
| 503 | `ANALYSIS_UNAVAILABLE` | false |
| 504 | `MODEL_TIMEOUT` | true |

FastAPI validation 오류도 원본 입력값이나 내부 필드 구조를 그대로 반환하지 않고
`INVALID_REQUEST`로 정규화한다. Python stack trace, 내부 경로, 원본 파일명,
transcript, Prompt, 토큰, Storage 정보와 라이브러리 오류 전문을 반환하지 않는다.

## 7. STT 계약

### 요청

```http
POST /internal/v1/analyses/stt
Content-Type: multipart/form-data
Authorization: Bearer {AI_SERVICE_TOKEN}
X-Request-Id: {UUID}
```

| Form 필드 | 형식 | 필수 |
|---|---|:---:|
| `answerId` | UUID | 예 |
| `language` | `ko` | 예 |
| `media` | MP4 또는 WebM | 예 |

### 성공 응답

```json
{
  "requestId": "00000000-0000-4000-8000-000000000001",
  "answerId": "00000000-0000-4000-8000-000000000002",
  "analysisType": "STT",
  "schemaVersion": "1.0",
  "modelVersion": "faster-whisper:{packageVersion}:base",
  "language": "ko",
  "transcript": "실제 모델이 생성한 전사 결과",
  "durationSec": 12.34
}
```

### 실제 구현

- 기존 `WhisperService`의 lazy singleton 모델 인스턴스를 재사용한다.
- 기본 모델 설정은 `WHISPER_MODEL_SIZE=base`다.
- 응답 modelVersion은 `faster-whisper:{packageVersion}:{WHISPER_MODEL_SIZE}`다.
- PyAV로 영상·음성 스트림과 실제 duration을 검증한다.
- faster-whisper 결과의 감지 언어가 `ko`와 다르면 성공 처리하지 않는다.
- 빈 transcript, 50,000자 초과 transcript, 비유한 duration을 거부한다.
- 모델·PyAV 준비 실패는 성공 응답이나 가짜 전사문으로 대체하지 않는다.

실제 Whisper 모델·GPU·동의된 E2E 미디어가 현재 검증 환경에는 준비되지 않아
실제 모델 E2E 성공은 확인하지 않았다. 서비스 경계와 HTTP 계약은 결정적
테스트 분석기를 통해 검증했지만 이를 실제 모델 E2E로 간주하지 않는다.

## 8. CV 계약

### 요청

`POST /internal/v1/analyses/cv`, multipart의 `answerId`, `media`를 사용한다.

향후 성공 DTO는 `gazeScore`, `postureScore`, `feedback`을 요구하고 점수는 각각
유한한 0~100이어야 한다.

현재 vision-server에는 Head Pose, 어깨, 상대 특징 등의 원시 지표만 있고
운영 GAZE·POSTURE 점수 산식이 없다. evidence 점수는 합성 `TEST_FIXTURE`이므로
운영 endpoint에 연결하지 않았다. 유효한 요청에도 503을 반환한다.

## 9. VOICE 계약

### 요청

`POST /internal/v1/analyses/voice`, multipart의 `answerId`, `media`를 사용한다.

향후 성공 DTO는 유한한 0~100 `speechScore`와 공개 가능한 `feedback`을
요구한다.

현재 speech/prosody 구현은 음향 원시 지표이며 운영 SPEECH 점수 산식이 없다.
TTS·음성 클론 결과는 VOICE 분석으로 사용하지 않는다. 유효한 요청에도 503을
반환한다.

## 10. CONTENT 계약

### 요청

```http
POST /internal/v1/analyses/content
Content-Type: application/json
```

```json
{
  "answerId": "00000000-0000-4000-8000-000000000002",
  "question": "현재 면접 질문",
  "transcript": "동일 답변의 STT 결과",
  "jobContext": null
}
```

- `question`, `transcript`: 비어 있을 수 없음
- transcript: 최대 50,000자
- question: 최대 5,000자
- jobContext: 선택, 최대 10,000자
- 선언하지 않은 Prompt·개인정보 필드: 거부

현재 LLM 제공자·모델·Prompt 소유자·평가 기준·점수 산식이 없으므로 유효한
요청에도 503을 반환한다. 고정 점수나 고정 피드백을 사용하지 않는다.

## 11. 미디어 전달 형식과 한도

기존 ANSWER 정책을 그대로 사용한다.

| 항목 | 정책 |
|---|---|
| MIME | `video/mp4`, `video/webm` |
| 실제 형식 | MP4 `ftyp`, WebM EBML 시그니처 |
| 최대 파일 크기 | 200MB |
| 최대 재생 시간 | 300초 |
| 스트림 | STT는 영상과 음성 스트림 모두 필수 |
| 원본 파일명 | 저장·로그·응답에 사용하지 않음 |

전체 요청을 애플리케이션 byte 배열로 읽지 않고 1MB 청크로 서버 임시 파일에
기록한다. Starlette multipart parser의 spooled upload를 사용하며 분석 서비스에는
서버 생성 경로만 전달한다.

## 12. 임시 파일 처리

- 기준 디렉터리: analysis-server의 `data/temp`
- 요청별 UUID 디렉터리와 고정 `media.mp4` 또는 `media.webm`
- 원본 파일명과 경로 순회 문자열 사용 금지
- 파일 저장 중 크기·시그니처 실패 시 즉시 삭제
- 성공·분석 실패 시 즉시 삭제
- timeout·요청 취소 시 실행 중 작업 종료 callback에서 삭제
- 원본 미디어·프레임·오디오 영구 저장 금지

## 13. timeout과 재시도

- 환경변수: `FACEFIT_AI_MODEL_TIMEOUT_SECONDS`
- 기본값: 55초
- Spring Worker 60초보다 작아야 하며 60초 이상 설정은 시작 시 거부
- HTTP 계층 자동 재시도 없음
- 504 `MODEL_TIMEOUT`만 `retryable=true`
- 실제 재시도는 기존 Spring Worker의 최대 3회, 2초·10초 정책에서 수행

## 14. 환경변수

```text
FACEFIT_AI_SERVICE_TOKEN
FACEFIT_AI_MODEL_TIMEOUT_SECONDS
FACEFIT_AI_MAX_UPLOAD_BYTES
FACEFIT_AI_MAX_DURATION_SECONDS
FACEFIT_AI_TRANSCRIPT_MAX_CHARS
WHISPER_MODEL_SIZE
WHISPER_DEVICE
WHISPER_COMPUTE_TYPE
CUDA_VISIBLE_DEVICES
PORT
LOG_LEVEL
```

실제 Secret 값은 예시 파일에 기록하지 않는다.

## 15. OpenAPI

결정적 OpenAPI 파일:

```text
ai-server/openapi/facefit-ai-openapi-v1.json
```

생성 명령:

```powershell
cd ai-server\analysis-server
python scripts\export_openapi.py
```

반복 생성 SHA-256이 동일한지 확인한다. 실제 FastAPI `/openapi.json`과 저장
파일을 테스트에서 구조적으로 비교한다.

OpenAPI는 STT만 HTTP 200 성공을 선언한다. CV·VOICE·CONTENT는 503 응답을
기본 응답으로 선언하여 아직 성공 가능한 분석인 것처럼 표시하지 않는다.

## 16. 테스트

### 신규 HTTP 계약 테스트

```powershell
python -m unittest `
  tests.test_analysis_http_api `
  tests.test_analysis_api_settings `
  tests.test_stt_http_analyzer -v
```

- 신규 테스트: 23개
- 성공: 23
- 실패·오류·Skip: 0
- 실제 Secret, 모델 또는 원본 사용자 미디어를 사용하지 않음

### analysis-server 전체 기존 테스트

기존 연구·CLI 테스트 677개와 신규 테스트 23개, 총 700개를 함께 실행했다.
전체 실행 결과는 성공 694개, 오류 6개, 실패·Skip 0개다. 오류 6개는 테스트
저장소에 고정 SHA-256이 요구하는 다음 비추적/제외 fixture가 존재하지 않아
발생했다.

- `data/input/audio/standard/speech_*.wav`
- `data/output/prosody/**`
- `data/output/prosody_v2/**`
- `data/output/prosody_validation/session_reports/**`

fixture를 가짜 파일로 생성하거나 고정 해시 테스트를 변경하지 않았다. 위 fixture
보존 검사 6개만 제외해 다시 실행한 694개는 모두 통과했고 실패·오류·Skip은 0개다.
PyAV 설치와 검증 중에만 적용한 Windows 줄바꿈 정규화 후 남은 오류는 위 fixture
부재에 따른 기존 테스트 선행조건 문제다. 이 범위는 HTTP 계약 테스트 성공으로
위장하지 않는다.

### Java 회귀

작업 전 PostgreSQL 16 Testcontainers와 Flyway V1~V6에서 기존 162개가 모두
통과했다. Python 변경 완료 후 같은 Maven 3.9.11 실행 파일로 `clean test`와
`clean verify`를 다시 실행했으며, 두 명령 모두 162개·실패 0·오류 0·Skip 0으로
`BUILD SUCCESS`였다.

## 17. 구현 완료와 미완료 구분

| 분석 | HTTP 계약 | 운영 성공 경로 | 실제 E2E |
|---|:---:|:---:|:---:|
| STT | 완료 | 기존 WhisperService 연결 | 미실행 |
| CV | 완료 | 없음, 503 | 해당 없음 |
| VOICE | 완료 | 없음, 503 | 해당 없음 |
| CONTENT | 완료 | 없음, 503 | 해당 없음 |

## 18. 아직 필요한 AI 담당자 결정

1. CV 원시 지표를 GAZE·POSTURE 0~100으로 변환하는 근거·임계값·결측 정책
2. VOICE 원시 speech/prosody 지표의 0~100 점수와 공개 피드백 정책
3. CONTENT LLM 제공자, 모델 버전, Prompt 소유자, 평가 rubric과 점수 산식
4. STT 운영 모델 크기, GPU 장치, compute type과 모델 파일 배포 방식
5. 실제 E2E용 동의된 MP4/WebM fixture와 기대 transcript 관리 방식
6. 누락된 기존 prosody 고정 fixture의 복구 또는 테스트 실행 프로필 분리

## 19. 11단계 Java Adapter 재개 범위

STT는 Method·URI·인증·multipart·성공·오류·버전 계약이 확정되어 Java Adapter
구현을 재개할 수 있다. 다만 실제 모델 E2E를 완료 전 운영 준비 완료로 판단하지
않는다.

CV·VOICE·CONTENT는 Java가 503 오류를 안전하게 분류하는 계약 테스트는 작성할
수 있으나, 성공 결과 Adapter는 Python 운영 산식·모델이 생기기 전까지 완료로
간주할 수 없다.

## 20. Ncloud 영상 저장소 전환에 따른 요청 계약 변경

면접 답변 미디어 전송은 `docs/19_FaceFit_Ncloud_영상_저장소_전환.md`를 우선한다. STT/CV/VOICE의 Method·URI와 응답 DTO·오류 코드는 유지하고, 내부 요청 Content-Type만 `multipart/form-data`에서 `application/json` Presigned URL 계약으로 변경했다. 저장 OpenAPI `ai-server/openapi/facefit-ai-openapi-v1.json`이 런타임 스키마와 일치해야 한다.
