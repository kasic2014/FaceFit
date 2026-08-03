# FaceFit 11단계 AI 서버 연동 정책 결정

- 확인일: 2026-07-31
- 대상: Spring Boot `STT`, `CV`, `VOICE`, `CONTENT` Port와 Python AI 서버
- 판정: **실제 HTTP 계약 미확정으로 Adapter 구현 중단**

## 결론

현재 저장소에는 Spring Boot가 안전하게 호출할 수 있는 STT·CV·VOICE·CONTENT
분석 HTTP 계약이 없다. 확인된 FastAPI endpoint는 각 서버의 `GET /health`뿐이며,
분석용 Router, 요청·응답 DTO, 인증, 파일 전달, 오류 응답 및 멱등성 계약은
구현되어 있지 않다.

따라서 이번 단계에서는 외부 URI, 인증 헤더 또는 JSON 필드를 추측하여 Java
HTTP Adapter를 만들지 않는다. 기존 Port·Worker·분석 결과·리포트 계약과
기본 비활성화 정책은 그대로 유지한다.

## 확인 범위

다음 위치를 코드와 문서 기준으로 확인했다.

- `ai-server/analysis-server`
- `ai-server/vision-server`
- `ai-server/tts-server`
- `FaceFit/ai-server`
- `backend/src/main/java/com/facefit/backend/interview/integration`
- `backend/src/main/java/com/facefit/backend/interview/application`
- `backend/src/main/java/com/facefit/backend/interview/storage`
- `backend/src/main/resources/application.yml`
- `backend/.env.example`
- `backend/README.md`
- `docs/FaceFit_백엔드_API_명세서_v0.3.md`
- `docs/12_FaceFit_연동요구사항_초안.md`
- `docs/14_FaceFit_10단계_분석리포트_정책결정.md`

## 확정된 계약

### Python 서버에서 코드로 확인된 HTTP endpoint

| 서버 | Method | URI | 응답 |
|---|---|---|---|
| analysis-server | GET | `/health` | `status`, `service` |
| vision-server | GET | `/health` | `status`, `service` |
| tts-server | GET | `/health` | `status`, `service` |

위 endpoint에는 인증이 적용되어 있지 않다. 분석 요청 endpoint로 사용할 수
없으며 Spring Boot의 네 분석 Port와 매핑되지 않는다.

### Spring Boot 내부 계약

- `SttPort.transcribe(AnswerAnalysisRequest)`
- `CvAnalysisPort.analyze(AnswerAnalysisRequest)`
- `VoiceAnalysisPort.analyze(AnswerAnalysisRequest)`
- `ContentAnalysisPort.analyze(AnswerAnalysisRequest)`
- Port 결과는 성공, 재시도 가능 실패, 영구 실패로 구분한다.
- STT 내부 결과는 `schemaVersion`과 `transcript`를 가진다.
- CV 내부 결과에는 `gazeScore`, `postureScore`와 공개 피드백이 필요하다.
- VOICE 내부 결과에는 `speechScore`와 공개 피드백이 필요하다.
- CONTENT 내부 결과에는 `contentScore`와 공개 피드백이 필요하다.
- 모든 점수는 0~100 범위여야 하며 원본 외부 payload는 저장하지 않는다.
- CONTENT는 동일 답변의 STT 성공 후에만 호출한다.
- 최초 실행을 포함한 Worker 최대 시도 횟수는 3회이고 재시도 간격은
  2초, 10초다.
- 조회 API는 외부 AI 서버를 호출하거나 작업을 새로 만들지 않는다.

## 코드에서 확인한 사실

### STT

- `WhisperService`와 `transcribe_turbo.py`는 로컬 파일을 대상으로
  faster-whisper를 실행할 수 있다.
- 현재 실행 형태는 Python 함수 또는 CLI이며 HTTP Router가 아니다.
- CLI 결과에는 transcript, 감지 언어, segment, word timestamp, 모델 및 실행
  진단값이 포함될 수 있으나, 이는 확정된 외부 API 응답 DTO가 아니다.
- HTTP 파일 필드명, 허용 Content-Type, 답변 식별자, schema/model version
  표기 방식, 최대 요청 크기 및 오류 응답 계약이 없다.

### CV

- vision-server에는 MediaPipe 기반 영상·랜드마크·Head Pose·어깨 원시 지표와
  세션 상대 특징 처리 코드가 있다.
- 현재 문서는 원시 지표가 사용자 시선·자세 점수 또는 면접 평가가 아님을
  명시한다.
- evidence scoring 결과는 `TEST_FIXTURE` 합성 자료이며 운영 점수로 사용할 수
  없다. 운영 모드는 fixture 사용을 거부한다.
- 0~100 `gazeScore`, `postureScore` 및 공개 피드백을 반환하는 실제 HTTP
  endpoint와 검증된 운영 점수 계약이 없다.

### VOICE

- analysis-server에는 speech/prosody 측정 코드가 있다.
- 해당 코드는 음향·발화 지표를 계산하지만 FaceFit 리포트용 0~100
  `speechScore`와 공개 피드백 계약을 제공하지 않는다.
- 분석 불가·침묵·입력 형식·모델 버전을 HTTP 오류와 응답 DTO로 표현하는
  계약이 없다.
- 음성 클론 TTS 서버는 이번 VOICE 말하기 분석 Port와 다른 기능이다.

### CONTENT

- 면접 질문과 동일 답변 transcript를 입력받아 0~100 `contentScore`와 공개
  피드백을 생성하는 구현 또는 HTTP endpoint를 찾을 수 없다.
- LLM 제공자, 모델, Prompt 경계, Prompt injection 방어, 개인정보 최소화,
  요청·응답 schema 및 오류 계약도 확인되지 않았다.

### HTTP·인증·Storage

- `app/api` 디렉터리는 `.gitkeep`만 있고 분석 Router가 없다.
- analysis-server의 `app/schemas`에는 실사용 요청·응답 DTO가 없다.
- 별도 OpenAPI 또는 Swagger 계약 파일이 없다.
- API Key, Bearer, mTLS 등 서버 간 인증 방식이 결정되어 있지 않다.
- `ai-server`의 환경 예시는 포트·CUDA·모델·로그 레벨만 정의한다.
- Spring Boot의 `InterviewAnswerStorage`는 업로드와 삭제만 지원하고 서버
  권한 다운로드 또는 스트리밍 조회 계약은 제공하지 않는다.
- `FaceFit/ai-server`는 루트 `ai-server`보다 HTTP 진입점과 환경 예시 등이
  부족한 별도 사본이다. 어느 디렉터리가 배포 기준인지 결정되지 않았다.

## 명세와 코드의 불일치

| 요구 계약 | 현재 코드 |
|---|---|
| STT 실제 HTTP Adapter 대상 endpoint | `/health` 외 분석 endpoint 없음 |
| CV `gazeScore`, `postureScore` | 원시/상대 지표만 존재, 운영 점수 없음 |
| VOICE `speechScore` | 실험적 음향 지표만 존재, 운영 점수 없음 |
| CONTENT `contentScore` | 분석 구현과 endpoint 없음 |
| 서버 간 인증 | 미구현·미결정 |
| multipart/JSON DTO | 미구현 |
| 외부 오류 응답과 재시도 분류 | 미구현 |
| 요청 추적·멱등성 | 미구현 |
| Storage 스트리밍 다운로드 | Backend Port 미지원 |
| 모델/schema 버전 응답 | Port 매핑 가능한 공통 계약 없음 |

## 결정이 필요한 항목

| 항목 | 필요한 결정 |
|---|---|
| 배포 기준 소스 | 루트 `ai-server`와 `FaceFit/ai-server` 중 단일 기준 |
| 서버 구성 | STT·VOICE·CONTENT를 한 서버에 둘지 분리할지 |
| Method·URI | 네 분석 endpoint의 실제 Method와 URI |
| 인증 | API Key, Bearer, mTLS 또는 내부 네트워크 정책 |
| 인증 헤더 | 인증 방식 확정 후 정확한 헤더 이름과 값 형식 |
| 파일 전달 | multipart 스트리밍, 짧은 만료 signed URL 또는 다른 방식 |
| 미디어 필드 | 파일 필드명, MIME, 파일명 정책, 최대 크기와 길이 |
| 식별자 | answerId·sessionId·questionId의 요청/응답 포함 여부 |
| 응답 schema | 필수 필드, null 허용, enum, score, feedback |
| 버전 | API schema version과 model version의 형식 및 호환 정책 |
| 오류 | 오류 envelope, 안정 코드, HTTP status, retryable 의미 |
| timeout | 서버별 처리 상한과 취소 시 실제 작업 중단 방식 |
| 멱등성 | 지원 여부와 키 전달 방법 |
| CONTENT 문맥 | 질문·전사문 외에 전달 가능한 최소 채용 문맥 |
| 개인정보 | CONTENT 전송 전 비식별화 책임과 필드 목록 |
| CV 점수 | 원시 지표를 0~100 점수로 만드는 검증된 운영 규칙 |
| VOICE 점수 | 음향 지표를 0~100 점수로 만드는 검증된 운영 규칙 |

## 구현을 막는 항목

다음 항목은 요청문에 정의된 중단 조건에 해당한다.

1. STT·CV·VOICE·CONTENT 실제 분석 endpoint가 없다.
2. 네 분석의 요청·응답 DTO가 없다.
3. AI 서버 인증 방식이 결정되지 않았다.
4. 영상·음성 파일 전달 방식이 결정되지 않았다.
5. CV·VOICE·CONTENT 결과를 기존 Port의 필수 점수에 매핑할 수 없다.
6. HTTP 오류 응답과 재시도 가능 여부를 판별할 계약이 없다.
7. Backend Storage Port에 비공개 원본 다운로드·스트리밍 기능이 없다.

## AI 담당자에게 확인할 질문

1. 운영 배포 기준은 `ai-server/`인가, `FaceFit/ai-server/`인가?
2. STT·CV·VOICE·CONTENT 각각의 실제 Method와 URI는 무엇인가?
3. 서버 간 인증 방식과 정확한 인증 헤더 계약은 무엇인가?
4. 서버는 multipart 스트리밍을 받는가, signed URL을 받는가?
5. STT가 MP4·WebM의 오디오를 직접 처리하는가, WAV 변환이 필요한가?
6. 각 endpoint의 최대 파일 크기, 최대 재생 시간, 허용 MIME은 무엇인가?
7. 요청과 응답에 answerId를 포함하며 서버가 동일 ID를 반사하는가?
8. API schema version과 model version의 필드명·형식은 무엇인가?
9. CV의 gaze/posture 0~100 점수는 어떤 검증된 규칙으로 생성되는가?
10. VOICE의 speech 0~100 점수는 어떤 검증된 규칙으로 생성되는가?
11. CONTENT에 허용되는 문맥은 질문과 transcript 외에 무엇인가?
12. 공개 가능한 feedback과 내부 진단정보의 구분 기준은 무엇인가?
13. 침묵, 얼굴 미검출, 자세 미검출, 분석 불가를 어떤 상태로 반환하는가?
14. 공통 오류 envelope와 안정적인 오류 코드 목록은 무엇인가?
15. 429·5xx 외에 재시도 가능한 오류가 있는가?
16. 멱등성 키 또는 요청 추적 ID를 공식 지원하는가?
17. 클라이언트 연결 종료나 timeout 발생 시 서버 작업은 취소되는가?
18. 서버 로그에서 원본 파일·transcript·Prompt·인증정보를 어떻게 차단하는가?

## 권장 계약안

아래 내용은 **검토용 권장안**이며 확정 계약이 아니다. AI 담당자 승인과 실제
Python Router·DTO 구현 전에는 Java 코드에 반영하지 않는다.

### 권장 공통 원칙

- 내부 전용 versioned endpoint를 사용한다.
- 파일 분석은 multipart 스트리밍, CONTENT는 JSON을 사용한다.
- 요청에는 무작위 상관관계 ID와 안정적인 작업 ID를 사용하되 Worker claim
  token은 전달하지 않는다.
- 응답은 요청의 `answerId`, `analysisType`, `schemaVersion`,
  `modelVersion`을 포함한다.
- 오류는 `code`, `retryable`, `requestId`만 외부 계약으로 사용하고 내부
  예외 원문과 URI는 포함하지 않는다.
- HTTP Client 자체 자동 재시도는 사용하지 않고 Backend Worker의 3회 정책만
  적용한다.

### 권장 endpoint 초안

| 분석 | 권장 Method | 권장 URI | 권장 입력 |
|---|---|---|---|
| STT | POST | `/internal/v1/analysis/stt` | multipart 미디어 + answerId |
| CV | POST | `/internal/v1/analysis/cv` | multipart 영상 + answerId |
| VOICE | POST | `/internal/v1/analysis/voice` | multipart 미디어 + answerId |
| CONTENT | POST | `/internal/v1/analysis/content` | JSON question + transcript + answerId |

### 권장 최소 응답 필드

- 공통: `answerId`, `analysisType`, `schemaVersion`, `modelVersion`
- STT: `language`, `transcript`
- CV: `gazeScore`, `postureScore`, `publicFeedback`
- VOICE: `speechScore`, `publicFeedback`, `analyzable`
- CONTENT: `contentScore`, `publicFeedback`

점수는 유한한 숫자 0~100만 허용한다. 공개 피드백 길이와 개수는 Backend의
정규화 한도와 맞춘다. segment, landmark, 특징 벡터, Prompt, 내부 진단 및
원본 모델 응답은 Backend로 반환하지 않는 것을 권장한다.

### 권장 미디어 전달

1. Backend가 DB에서 답변과 세션 소유권을 다시 확인한다.
2. 서버 권한으로 Private Storage 원본을 연다.
3. 전체 byte 배열 또는 공개 URL 없이 제한된 스트림으로 AI 서버에 전달한다.
4. 서버가 생성한 고정 파일명과 검증된 MIME만 multipart에 사용한다.
5. 전송·응답 제한과 timeout을 적용하고 모든 스트림을 닫는다.

이를 위해 실제 계약 확정 후 `InterviewAnswerStorage`에 크기 제한이 있는
서버 전용 스트리밍 읽기 기능이 필요할 수 있다. Supabase secret, bucket,
object key 및 signed URL은 AI 응답이나 사용자 API에 포함하지 않는다.

## 이번 단계에서 수행하지 않은 구현

- Java 공통 AI HTTP Client
- STT·CV·VOICE·CONTENT HTTP Adapter
- 외부 요청·응답 DTO와 Mapper
- 인증 헤더 주입
- Storage 다운로드·스트리밍 확장
- Adapter 활성화 환경변수
- HTTP 계약 테스트
- 실제 AI 서버 E2E
- Flyway V7

위 항목은 계약을 확인하지 못했기 때문에 완료로 간주하지 않는다.

## 재개 조건

다음 자료가 하나의 기준 문서 또는 실행 가능한 Python 코드로 제공되면 11단계
구현을 재개한다.

1. 네 분석 endpoint와 요청·응답 DTO
2. 인증 및 파일 전달 계약
3. 오류 envelope와 retryable 분류
4. schema/model version 정책
5. CV·VOICE·CONTENT 운영 점수 계약
6. 배포 기준 AI 서버 디렉터리
7. 실제 endpoint를 검증하는 Python HTTP 테스트 또는 OpenAPI
