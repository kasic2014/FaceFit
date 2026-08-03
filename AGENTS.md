# FACE-FIT 백엔드 API 고정 규칙

## 적용 기준

- 기준 명세: `C:\Users\SMHRD\Documents\실전 프로젝트\docs\FaceFit_백엔드_API_명세서_v0.3.md`
- 이후 API 구현·문서화·컨트롤러 작성 시 아래의 API ID, HTTP Method, URI 조합을 임의로 변경하지 않는다.
- 변경이 필요하면 먼저 **변경 전 / 변경 후 / 변경 이유 / 영향 API**를 제시하고 사용자 승인을 받는다.
- API ID가 같은데 Method 또는 URI가 다르면 새 API를 만들거나 추정하지 말고 명세 충돌로 보고한다.

## 현재 구현 대상의 Method·URI

| API ID | Method | URI |
|---|---|---|
| AUTH-001 | GET | `/oauth2/authorization/{provider}` |
| AUTH-002 | GET | `/login/oauth2/code/{provider}` |
| AUTH-003 | POST | `/api/v1/auth/oauth/exchange` |
| AUTH-004 | POST | `/api/v1/auth/token/refresh` |
| AUTH-005 | POST | `/api/v1/auth/logout` |
| AUTH-006 | GET | `/api/v1/auth/session` |
| LEGAL-001 | GET | `/api/v1/legal-documents` |
| LEGAL-002 | GET | `/api/v1/legal-documents/{documentId}` |
| ONBOARDING-001 | PATCH | `/api/v1/members/me/onboarding` |
| MEMBER-001 | GET | `/api/v1/members/me` |
| DOC-001 | POST | `/api/v1/career-documents` |
| DOC-002 | GET | `/api/v1/career-documents` |
| DOC-003 | GET | `/api/v1/career-documents/{documentId}` |
| DOC-004 | DELETE | `/api/v1/career-documents/{documentId}` |
| JOB-001 | POST | `/api/v1/job-postings` |
| JOB-002 | GET | `/api/v1/job-postings` |
| JOB-003 | GET | `/api/v1/job-postings/{jobPostingId}` |
| JOB-004 | PATCH | `/api/v1/job-postings/{jobPostingId}` |
| JOB-005 | DELETE | `/api/v1/job-postings/{jobPostingId}` |
| SESSION-001 | POST | `/api/v1/interview-sessions` |
| SESSION-002 | GET | `/api/v1/interview-sessions/{sessionId}` |
| SESSION-003 | PATCH | `/api/v1/interview-sessions/{sessionId}` |
| SESSION-004 | POST | `/api/v1/interview-sessions/{sessionId}/start` |
| SESSION-005 | POST | `/api/v1/interview-sessions/{sessionId}/completion` |
| QUESTION-001 | GET | `/api/v1/interview-sessions/{sessionId}/questions/current` |
| ANSWER-001 | POST | `/api/v1/interview-sessions/{sessionId}/answers` |
| ANSWER-002 | GET | `/api/v1/interview-answers/{answerId}` |
| ANALYSIS-001 | GET | `/api/v1/interview-sessions/{sessionId}/analysis-status` |
| REPORT-001 | GET | `/api/v1/interview-sessions/{sessionId}/report` |
| HISTORY-001 | GET | `/api/v1/members/me/interview-sessions` |
| GROWTH-001 | GET | `/api/v1/members/me/growth` |
| VOICE-001 | POST | `/api/v1/voice-profiles` |
| VOICE-002 | GET | `/api/v1/voice-profiles/me` |
| VOICE-003 | DELETE | `/api/v1/voice-profiles/me` |

## 현재 제외·보류된 이전 흐름

| API ID | Method | URI | 처리 기준 |
|---|---|---|---|
| REG-001 | POST | `/api/v1/member-registrations` | 삭제된 v0.1 이력이다. PENDING 가입 완료 흐름을 재도입하지 않는 한 구현하지 않는다. |

## 현재 프로젝트 결정과의 정합성

- OAuth 최초 로그인은 PENDING 단계를 사용하지 않고 `ACTIVE` 회원을 자동 생성한다.
- 회원 상태와 별도로 `onboardingStatus`를 관리하고, 미완료 회원은 `ONBOARDING-001`로 첫 이용 절차를 완료한다.
- `memberStatus=PENDING`, 가입 완료 전용 처리, PENDING 전용 토큰·화면 전환은 다시 승인받지 않는 한 추가하지 않는다.
- 지원공고 URL 수집·크롤링·스크래핑은 구현하지 않는다.
- 지원공고는 `JOB-001~005`를 통해 사용자가 제공한 파일(`FILE`) 또는 일반 텍스트(`TEXT`)로 입력받는다.
- `JOB-001`의 `FILE` 입력은 `multipart/form-data`, `TEXT` 입력은 `application/json`을 사용하며 두 입력을 한 요청에 함께 보내지 않는다.
- 지원공고 파일은 PDF·DOCX·JPG·JPEG·PNG·HWP 5.x만 허용한다. HWP 2.x·3.x, HWPX, 암호화·비밀번호 보호·배포용·손상·위장 HWP는 허용하지 않는다.
- 업로드 파일의 확장자·MIME 타입·실제 형식을 검증하고 파일이나 `rawText`에 포함된 매크로·스크립트·명령문은 실행하지 않는다.
- 지원공고 URL, 외부 사이트 크롤링·스크래핑 및 `SCRIPT` 입력은 허용하지 않는다.
- `CAREER_DOCUMENTS.documentType`에는 `RESUME`, `COVER_LETTER`만 사용하고 `JOB_POSTING`은 사용하지 않는다.
- 면접 세션 생성에는 본인 소유의 `READY` 이력서와 필수 확인값이 채워진 `READY` 지원공고가 필요하며, 자기소개서는 선택 사항이다.
- 면접 세션은 `jobPostingId`를 참조하고 지원공고 구조화 정보 8개를 세션 스냅샷으로 저장한다. 원본 수정은 기존 스냅샷에 반영하지 않고 `DRAFT` 설정 수정에서 공고를 바꿀 때만 전체 교체한다.
- 비종료 면접 세션(`DRAFT`, `IN_PROGRESS`, `INTERVIEW_COMPLETED`, `ANALYZING`)이 참조하는 경력 문서와 지원공고는 삭제하지 않는다.
- 면접 언어는 한국어로 고정하며 별도 언어 컬럼·요청 필드를 추가하지 않는다.
- 면접 시작은 비동기 질문 생성 작업을 등록하고 질문 10개가 모두 저장될 때까지 세션을 `DRAFT`로 유지한다.
- 답변은 영상·음성 스트림이 모두 있는 MP4·WebM만 허용하며, 최대 200MB·300초로 제한하고 `interview-answers` Private bucket에 저장한다.
- `SESSION-004`, `ANSWER-001`, `SESSION-005`는 확정된 `Idempotency-Key` 계약을 적용한다.
- `NORMAL` 종료는 답변 10개 저장 여부로 판단하고 개별 분석 상태와 분리하며, 사용자 중단은 `INTERRUPTED`로 기록한다.
- 정상 종료 세션은 답변별 `STT`, `CV`, `CONTENT`를 분석하고, 해당 세션 생성 시 음성 분석에 동의한 경우에만 `VOICE` 분석을 추가한 뒤 `INTERVIEW_COMPLETED → ANALYZING → COMPLETED`로 전환한다.
- 같은 답변의 `CONTENT` 작업은 `STT` 성공 후에만 실행하며 STT 최종 실패 시 외부 호출 없이 `DEPENDENCY_FAILED`로 종료한다.
- `ANALYSIS-001`은 고정 URI `/api/v1/interview-sessions/{sessionId}/analysis-status`에서 작업 수 기준 진행률과 안전한 실패 상태를 제공한다.
- `REPORT-001`은 모든 필수 분석 성공 후 비동기 `REPORT_GENERATION` 작업이 확정 저장한 세션당 단일 리포트만 조회한다.
- 최종 리포트의 각 사용 축 점수는 답변 10개의 산술평균을 소수점 첫째 자리에서 `HALF_UP` 반올림한다. 음성 분석 동의 시 `GAZE`, `POSTURE`, `SPEECH`, `CONTENT` 네 축을, 미동의 시 `SPEECH=null`로 두고 `GAZE`, `POSTURE`, `CONTENT` 세 축을 동일 가중치로 집계한다.
- 부분 리포트와 실패 분석의 0점 대체는 허용하지 않으며, 중단 세션은 분석 조정과 리포트 생성에서 제외한다.
- 내부 AI HTTP 계약은 `docs/16_FaceFit_12단계_AI_HTTP계약.md`를 기준으로 하며 루트 `ai-server/analysis-server`가 단일 HTTP 진입점이다. STT는 실제 WhisperService 경계를 사용하고 CV·VOICE·CONTENT는 운영 산식·모델이 확정될 때까지 `503 ANALYSIS_UNAVAILABLE`을 반환한다. Spring HTTP Adapter는 아직 구현하지 않았다.
- `VOICE-001~003` 음성 클론은 이번 MVP 구현 범위에 포함한다.
- 음성 분석 동의는 온보딩의 선택 항목이며 미동의여도 음성 분석을 제외한 모든 면접 서비스를 사용할 수 있다. 음성 클론용 음성정보 동의는 이 항목 및 온보딩 필수 동의와 분리하고, 유효한 별도 동의가 있어야 `VOICE-001`을 호출할 수 있다.
- 음성 복제 작업은 비동기로 처리하고 샘플·미리듣기·외부 모델 삭제 상태까지 추적한다.

## 공통 제약

- JSON API 기본 경로는 `/api/v1`을 사용한다. OAuth 시작·Callback 경로는 위 표의 예외 경로를 유지한다.
- 리소스 ID Path Variable 이름은 표의 `{provider}`, `{documentId}`, `{jobPostingId}`, `{sessionId}`, `{answerId}` 표기를 유지한다.
- 파일 업로드 API는 `multipart/form-data`, 그 외 일반 API는 `application/json`을 기본으로 한다. 단, 실제 명세에 따라 예외가 있으면 해당 명세를 우선한다.
- 본인 소유 문서·면접 세션·답변·결과만 접근하도록 인가를 적용한다.
