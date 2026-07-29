# FACE-FIT 백엔드 API 고정 규칙

## 적용 기준

- 기준 명세: `C:\Users\SMHRD\Documents\실전 프로젝트\FaceFit_백엔드_API_명세서_v0.3.md`
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
- 지원공고는 `JOB-001~005`를 통해 사용자가 제공한 파일(`FILE`) 또는 일반 텍스트(`TEXT`)로 입력받는다. 텍스트는 코드로 실행하지 않는다.
- `CAREER_DOCUMENTS.documentType`에는 `RESUME`, `COVER_LETTER`만 사용하고 `JOB_POSTING`은 사용하지 않는다.
- 면접 세션은 `jobPostingId`를 참조하고 회사명, 지원 직무, 주요 업무, 자격요건 등의 확인값을 세션 스냅샷으로 저장한다.
- 면접 언어는 한국어로 고정하며 별도 언어 컬럼·요청 필드를 추가하지 않는다.
- `VOICE-001~003` 음성 클론은 이번 MVP 구현 범위에 포함한다.
- 음성정보 동의는 온보딩 필수 동의와 분리하고, 유효한 별도 동의가 있어야 `VOICE-001`을 호출할 수 있다.
- 음성 복제 작업은 비동기로 처리하고 샘플·미리듣기·외부 모델 삭제 상태까지 추적한다.

## 공통 제약

- JSON API 기본 경로는 `/api/v1`을 사용한다. OAuth 시작·Callback 경로는 위 표의 예외 경로를 유지한다.
- 리소스 ID Path Variable 이름은 표의 `{provider}`, `{documentId}`, `{sessionId}`, `{answerId}` 표기를 유지한다.
- 파일 업로드 API는 `multipart/form-data`, 그 외 일반 API는 `application/json`을 기본으로 한다. 단, 실제 명세에 따라 예외가 있으면 해당 명세를 우선한다.
- 본인 소유 문서·면접 세션·답변·결과만 접근하도록 인가를 적용한다.
