# FACE-FIT Backend

Java 21과 Spring Boot 3.5 기반의 FACE-FIT 백엔드입니다. 인증은 Supabase Auth가 발급한 Access Token을 검증하는 OAuth2 Resource Server 방식입니다.

## 로컬 준비

1. `.env.example`을 참고해 실행 환경변수를 설정합니다.
2. Java 21을 사용합니다.
3. `mvnw.cmd test` 또는 `./mvnw test`로 테스트합니다.
4. `mvnw.cmd spring-boot:run` 또는 `./mvnw spring-boot:run`으로 실행합니다.

애플리케이션은 `.env` 파일을 자동으로 읽지 않습니다. IDE 실행 설정, 운영체제 환경변수 또는 별도의 안전한 비밀 관리 수단으로 값을 주입해야 합니다.

## 인증 확인

Supabase Access Token을 다음과 같이 전달합니다.

```http
GET /api/v1/auth/me
Authorization: Bearer {SUPABASE_ACCESS_TOKEN}
```

Spring Boot는 OAuth Redirect·Callback, 자체 JWT 또는 Refresh Token을 발급하지 않습니다.

## 지원공고 OCR 준비

지원공고 이미지와 스캔 PDF OCR은 운영 환경에 설치된 Tesseract CLI를 사용합니다. Tesseract 실행 파일과 `kor`, `eng` 학습 데이터를 별도로 설치한 뒤 다음 환경변수를 설정합니다. 바이너리와 학습 데이터는 저장소에 포함하지 않습니다.

```env
JOB_POSTING_OCR_ENABLED=true
TESSERACT_EXECUTABLE=tesseract
TESSDATA_PREFIX=
JOB_POSTING_OCR_LANGUAGES=kor+eng
JOB_POSTING_OCR_TIMEOUT_SECONDS=120
JOB_POSTING_HWP_TIMEOUT_SECONDS=30
JOB_POSTING_HWP_MAX_HEAP_MB=256
```

실행 파일 또는 학습 데이터가 없더라도 애플리케이션은 부팅됩니다. 해당 OCR 작업만 안정적인 내부 오류 코드로 `FAILED` 처리됩니다.

HWP 5.x 파싱은 Apache Tika `HwpV5Parser`를 별도 Java 프로세스에서 실행합니다.
기본 30초 제한시간과 256MB 최대 힙을 적용하며, 설정 가능한 최대 힙은 512MB로 제한됩니다.
원본과 추출 결과는 UUID 임시 경로에만 기록하고 처리 종료 시 삭제합니다.

## 면접 설정 API

`SESSION-001~003`은 인증된 `ACTIVE` 회원이 온보딩을 완료한 경우에만
사용할 수 있습니다. 본인 소유의 `READY` 이력서와 지원공고가 필수이고,
`READY` 자기소개서는 선택입니다. 지원공고는 회사명·지원 직무·주요 업무·
자격요건이 모두 채워져 있어야 합니다.

세션 생성 시 지원공고 구조화 정보 8개를 `interview_sessions`에 스냅샷으로
저장합니다. 원본 공고 수정은 기존 스냅샷에 영향을 주지 않으며,
`SESSION-003`에서 공고를 변경할 때만 전체 스냅샷을 교체합니다. 설정 수정은
`DRAFT`에서만 가능하고, 비종료 세션에서 사용 중인 경력 문서·지원공고는
`DOC-004`·`JOB-005`로 삭제할 수 없습니다.

## 면접 진행 API

`SESSION-004~005`, `QUESTION-001`, `ANSWER-001~002`를 구현합니다.
면접 시작은 질문 생성 작업을 비동기로 등록하고, 검증된 질문 10개가 모두
저장된 경우에만 세션을 `IN_PROGRESS`로 전환합니다. 시작·답변·종료
요청에는 `Idempotency-Key`가 필요합니다.

답변은 영상·음성 스트림이 모두 있는 MP4 또는 WebM만 허용하며 최대
200MB·300초입니다. 원본은 `interview-answers` Private bucket에
저장합니다. 운영 bucket은 Public 접근과 파일 덮어쓰기를 비활성화해야
합니다.

질문 생성, STT, CV, 음성 및 내용 분석의 내부 Port와 비동기 작업 구조는
구현되어 있습니다. 실제 외부 URI·인증·제공자 JSON은 아직 확정되지 않아
운영 Adapter와 E2E 호출은 포함하지 않습니다. 실제 Adapter가 연결되기
전에는 다음 설정을 `false`로 유지합니다.

정상 종료 세션은 답변 분석을 조정한 뒤
`INTERVIEW_COMPLETED → ANALYZING → COMPLETED`로 전환합니다. CONTENT는
같은 답변의 STT 성공 후에만 실행합니다. 모든 필수 분석이 성공하면
`REPORT_GENERATION` Worker가 GAZE·POSTURE·SPEECH·CONTENT 네 축을
결정적으로 집계하고 리포트 저장과 `COMPLETED` 전환을 한 트랜잭션으로
처리합니다. 부분 리포트와 실패 점수의 0점 대체는 지원하지 않습니다.

분석 상태는 `GET /api/v1/interview-sessions/{sessionId}/analysis-status`,
최종 리포트는 `GET /api/v1/interview-sessions/{sessionId}/report`에서
조회합니다. 조회 API는 새 작업이나 리포트를 생성하지 않습니다.

```env
INTERVIEW_ANSWERS_BUCKET=interview-answers
INTERVIEW_PROCESSING_DISPATCH_ENABLED=false
INTERVIEW_PROCESSING_RECOVERY_ENABLED=false
INTERVIEW_QUESTION_TIMEOUT_SECONDS=60
INTERVIEW_STT_TIMEOUT_SECONDS=120
INTERVIEW_ANALYSIS_TIMEOUT_SECONDS=60
INTERVIEW_REPORT_TIMEOUT_SECONDS=60
```

지원공고 FILE 원본은 `job-postings` Private Supabase Storage bucket을 사용합니다. 버킷은 최대 10MB와 다음 MIME만 허용하도록 운영 환경에서 설정해야 합니다.

```text
application/pdf
application/vnd.openxmlformats-officedocument.wordprocessingml.document
image/jpeg
image/png
application/x-hwp-v5
```
