# FaceFit 백엔드 API 명세서 v0.3.6

| 항목 | 내용 |
| --- | --- |
| 문서 목적 | 백엔드 구현 및 프론트엔드·AI 담당자와의 연동 기준 공유 |
| 기준 자료 | FACE-FIT 기획서·화면설계서, API 명세서 v0.1, 테이블 명세서 v0.3, 사용자 확정 정책 |
| 작성 범위 | 백엔드 공개 API, Agentic RAG·이력서 분석·질문 생성의 내부 연동 경계 |
| 제외 범위 | 모델 학습 방식, 제공자별 비공개 추론 알고리즘, 비공개 prompt 원문 |
| 버전 | v0.3.6 |
| 작성일 | 2026-07-28 |
| 최종 수정일 | 2026-07-31 |

> v0.3.6에서는 MuseTalk 질문 영상과 답변 근거 영상에 `PlaybackAccess`·opaque token Range streaming을 도입하고, AI worker HTTP callback·통합 오류 코드·AI 직무 범위·VAD 종료 기준 및 필수 지원공고 FILE(PDF·캡처 이미지) 입력을 확정합니다.

> 계약 우선순위: 같은 문서 안에서 요약 표와 상세 계약이 충돌하면 `12. 프론트엔드 통합 확정 계약`을 우선합니다. 제품 문서와 충돌하면 본 문서 v0.3.6의 명시적 확정 항목을 우선하며 충돌 문서를 후속 동기화합니다.

## 1. 기존 명세 대비 주요 변경 사항

| 구분 | 변경 전 | 변경 후 |
| --- | --- | --- |
| 신규 OAuth 회원 | `PENDING` 생성 | `ACTIVE` 회원 생성 및 `onboardingStatus=NOT_STARTED` |
| 가입 완료 API | `REG-001 POST /api/v1/member-registrations` | 제거 |
| 온보딩 API | 없음 | `ONBOARDING-001 PATCH /api/v1/members/me/onboarding` |
| 지원공고 | `CAREER_DOCUMENTS.documentType=JOB_POSTING` | 독립된 `JOB_POSTINGS` 리소스 |
| 지원공고 입력 | 지원공고 URL 또는 스크립트 입력 후보 | 사용자 필수 FILE: PDF 또는 캡처 이미지(JPG·JPEG·PNG) |
| 지원공고 URL | 후보 범위에 포함될 수 있었음 | 수집·크롤링·스크래핑하지 않음 |
| 언어 설정 | 세션 요청에 언어 포함 | 한국어 고정, 언어 필드 제거 |
| AI 대기 상태 | `PENDING` | `QUEUED` |
| 음성 프로필 | MVP 포함 여부 미확정 | V1 제외, 후속 선택 기능 |
| 음성 동의 | 추후 정책 | 온보딩 필수 동의와 분리된 기능 이용 동의 |
| 음성 처리 | 후보 수준 | 샘플 업로드, 비동기 복제, 상태 조회, 삭제까지 구현 |
| 질문 수 | 10개 고정 후보 | 기본 질문 5개 + 각 기본 질문당 꼬리질문 0~1개, 총 5~10턴 |
| 캐릭터 면접관 | 실시간 연결 후보 | TTS+MuseTalk 질문 단위 MP4, HTTPS polling·streaming |
| 기능별 동의 | 조회만 존재 | 생성·철회와 세션 context 계약 추가 |
| 데이터 삭제 | 리소스별 일부 삭제 | 미디어·회원 삭제와 완료 상태 조회 추가 |
| 분석 실패 | 조회만 존재 | 사용자 재시도 API 추가 |
| 개선 음성 | 재생 계약 없음 | 표준·개인 음성 binary streaming 추가 |
| 프론트 route | session 식별자 없음 | `/sessions/:sessionId/*` 계약 확정 |
| 질문 생성 | 일반 LLM 경계만 정의 | Agentic RAG·이력서 profile·prompt version·근거 추적 계약 추가 |

### 1.1 명시적 제외 사항

- 회원 상태로서의 `PENDING`
- `REG-001` 및 `/api/v1/member-registrations`
- 지원공고 URL 수집, 외부 사이트 크롤링·스크래핑
- 지원공고 URL·스크립트 입력
- 지원공고 일반 텍스트·DOCX·HWP 입력
- 업로드된 파일에 포함된 매크로·스크립트·명령문의 서버 실행
- `CAREER_DOCUMENTS`의 `JOB_POSTING` 문서 유형
- 면접 언어 선택 기능

## 2. 백엔드가 담당하는 핵심 작업

- OAuth 로그인, 신규 회원 자동 생성, 인증정보 발급·갱신·로그아웃
- 계정 상태와 온보딩 진행 상태의 분리 관리
- 최신 필수 법률 문서 제공 및 온보딩 동의 기록
- 이력서·선택 자기소개서 파일 저장과 처리 상태 관리
- 이력서에서 면접용 경험·역할·성과·기술 근거를 구조화하고 민감정보를 제거
- 승인된 공식 기업 자료와 지원공고를 RAG index에서 검색해 질문 근거로 연결
- 제한된 tool·budget·prompt version을 가진 질문 생성 Agent와 꼬리 질문 Agent 실행
- 사용자가 제공한 지원공고 PDF 또는 캡처 이미지(JPG·JPEG·PNG) 검증·비공개 저장
- 스크린샷 이미지 OCR 또는 PDF 텍스트 추출과 구조화 상태 관리
- 지원공고의 회사명·직무·주요 업무·자격요건 등 사용자 확인값 관리
- 면접 설정, 질문 순서, 답변 제출, 면접 진행 상태 관리
- 답변 영상·음성 파일 저장 및 AI 서버 전달
- 문서 파싱, 지원공고 파싱, STT·CV·발화·내용 분석 작업 요청과 결과 저장
- 후속 음성 프로필 기능의 별도 동의·샘플·삭제 계약 관리
- 분석 진행 상태, 리포트, 면접 이력, 성장 데이터 제공
- 본인 소유 데이터 검증, 파일 접근 제한, 오류와 재시도 상태 관리

## 3. API 공통 규칙

### 3.1 기본 규칙

| 구분 | 규칙 |
| --- | --- |
| 기본 경로 | JSON API는 `/api/v1` 사용 |
| OAuth 예외 경로 | `/oauth2/authorization/{provider}`, `/login/oauth2/code/{provider}` 유지 |
| 인증 | `Authorization: Bearer {accessToken}` 사용 |
| 파일 요청 | `multipart/form-data` 사용 |
| 일반 요청 | `application/json` 사용 |
| 필드명 | `camelCase` 사용 |
| 식별자 | UUID 문자열 사용 |
| 날짜·시간 | ISO 8601 형식 사용 |
| 언어 | 면접·STT 기본 언어는 한국어로 고정하고 별도 언어 필드를 받지 않음 |
| 권한 | 현재 로그인한 사용자의 데이터만 조회·수정·삭제 가능 |
| AI 처리 | 긴 작업은 비동기로 실행하고 상태 조회 API 제공 |
| 지원공고 입력 | 필수 `FILE`; PDF 또는 캡처 이미지(JPG·JPEG·PNG)만 허용 |
| 지원공고 파일 처리 | 확장자·MIME 타입·실제 파일 형식을 검증하고 파일에 포함된 코드를 실행하지 않음 |

### 3.2 공통 성공 응답

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "요청이 정상적으로 처리되었습니다.",
  "data": {}
}
```

### 3.3 공통 오류 응답

```json
{
  "success": false,
  "code": "VALIDATION_FAILED",
  "message": "입력값을 확인해주세요.",
  "data": null
}
```

### 3.4 주요 상태값

| 대상 | 상태값 | 의미 |
| --- | --- | --- |
| 회원 | `ACTIVE` | 로그인 및 서비스 이용 가능한 계정 |
| 회원 | `BLOCKED`, `WITHDRAWN` | 이용 제한 또는 탈퇴 상태 |
| 온보딩 | `NOT_STARTED` | 첫 이용 절차를 시작하지 않음 |
| 온보딩 | `IN_PROGRESS` | 첫 이용 절차 진행 중 |
| 온보딩 | `COMPLETED` | 필수 온보딩 완료 |
| 경력 문서 | `PROCESSING`, `READY`, `FAILED` | 문서 처리 중, 완료, 실패 |
| 지원공고 | `PROCESSING`, `READY`, `FAILED` | 파일 추출·구조화 중, 사용 가능, 실패 |
| 면접 | `DRAFT`, `IN_PROGRESS`, `INTERVIEW_COMPLETED`, `ANALYZING`, `COMPLETED`, `INTERRUPTED` | 설정, 진행, 면접 종료, 분석, 완료, 중단 |
| 답변 | `UPLOADED`, `PROCESSING`, `READY`, `FAILED` | 답변 업로드 확정부터 처리 완료까지의 상태 |
| 분석 작업 | `QUEUED`, `PROCESSING`, `PARTIAL`, `COMPLETED`, `FAILED` | 대기, 처리 중, 일부 완료, 전체 완료, 실패 |
| 음성 프로필 | `QUEUED`, `PROCESSING`, `READY`, `FAILED`, `DELETING` | 생성 대기, 생성 중, 사용 가능, 생성 실패, 삭제 중 |

## 4. 전체 API 목록

공개 API는 총 49개입니다. 4.1~4.8은 기능별 요약이며 11절이 고정 registry,
12절이 요청·응답·캐릭터 미디어 통합 상세 계약입니다.

### 4.1 인증·온보딩·법률 문서·회원

| ID | Method | URI | 기능 | 인증 | 프론트 요청 | 주요 응답 | 백엔드 역할 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUTH-001 | GET | `/oauth2/authorization/{provider}` | OAuth 로그인 시작 | 불필요 | `provider` | OAuth 화면 이동 | 제공자 인증 화면으로 리다이렉트 |
| AUTH-002 | GET | `/login/oauth2/code/{provider}` | OAuth Callback 처리 | 제공자 Callback | `code`, `state` | 프론트로 로그인 티켓 전달 | OAuth 검증, 기존 회원 조회, 신규 회원 `ACTIVE` 생성 |
| AUTH-003 | POST | `/api/v1/auth/oauth/exchange` | 로그인 티켓 교환 | 불필요 | `loginTicket` | 인증정보, 회원·온보딩 상태, `nextAction` | 일회용 티켓 검증 후 현재 서버 상태에 맞는 인증 결과 제공 |
| AUTH-004 | POST | `/api/v1/auth/token/refresh` | 인증정보 갱신 | 갱신 쿠키 | 없음 | 새 인증정보, 회원·온보딩 상태 | 서버의 현재 회원 상태를 확인한 뒤 인증정보 갱신 |
| AUTH-005 | POST | `/api/v1/auth/logout` | 로그아웃 | 필요 | 없음 | 없음 | 현재 로그인 세션과 갱신 인증정보 무효화 |
| AUTH-006 | GET | `/api/v1/auth/session` | 현재 인증 상태 조회 | 선택 | 없음 | 인증 여부, 회원·온보딩 상태, `nextAction` | 프론트의 로그인·온보딩·서비스 화면 분기 지원 |
| LEGAL-001 | GET | `/api/v1/legal-documents` | 현재 법률 문서 목록 | 불필요 | `type` 선택 | 문서 ID, 종류, 버전, 온보딩 필수 여부 | 현재 적용 중인 약관·개인정보 문서 제공 |
| LEGAL-002 | GET | `/api/v1/legal-documents/{documentId}` | 법률 문서 상세 | 불필요 | `documentId` | 제목, 버전, 본문, 필요 행위 | 선택한 문서 내용 제공 |
| ONBOARDING-001 | PATCH | `/api/v1/members/me/onboarding` | 내 온보딩 완료 처리 | 필요 | 최신 필수 문서 동의·고지 확인 목록, 선택 `voiceAnalysisConsent` | `onboardingStatus=COMPLETED`, `voiceAnalysisConsent`, `nextAction` | 최신 필수 조건 검증, 법률 기록 저장, 선택 음성 분석 동의 저장, 온보딩 완료 처리 |
| MEMBER-001 | GET | `/api/v1/members/me` | 내 프로필 조회 | 필요 | 없음 | 회원 ID, 이름, 이메일, 회원·온보딩 상태 | 현재 사용자의 최소 프로필 제공 |

#### 신규 회원 정상 흐름

```text
AUTH-001
→ AUTH-002 OAuth 검증 및 ACTIVE 회원 자동 생성
→ AUTH-003 로그인 티켓 교환
→ onboardingStatus 확인
→ 미완료이면 LEGAL-001~002 및 ONBOARDING-001
→ AUTH-006 상태 확인
→ 서비스 화면 이동
```

#### `nextAction`

| 값 | 의미 |
| --- | --- |
| `COMPLETE_ONBOARDING` | 온보딩 화면 이동 |
| `GO_TO_SERVICE` | 서비스 화면 이동 |
| `RELOGIN` | OAuth 로그인 재진행 |

#### AUTH-003 주요 응답 예시

```json
{
  "memberStatus": "ACTIVE",
  "onboardingStatus": "NOT_STARTED",
  "accessToken": "access-token",
  "nextAction": "COMPLETE_ONBOARDING"
}
```

#### ONBOARDING-001 요청 예시

```json
{
  "voiceAnalysisConsent": false,
  "legalActions": [
    {
      "documentId": "legal-document-uuid",
      "actionType": "CONSENTED"
    },
    {
      "documentId": "privacy-document-uuid",
      "actionType": "ACKNOWLEDGED"
    }
  ]
}
```

온보딩 완료에 포함할 추가 프로필 입력값은 현재 명세에서 확정하지 않습니다. MVP에서는 최신 필수 법률 문서에 필요한 행위를 완료했는지를 기준으로 합니다.

### 4.2 이력서·자기소개서

| ID | Method | URI | 기능 | 프론트 요청 | 주요 응답 | 백엔드 역할 | AI 연동 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DOC-001 | POST | `/api/v1/career-documents` | 경력 문서 등록 | `file`, `documentType` | `documentId`, `status` | 파일 검증·저장, 사용자 소유권 연결, 문서 처리 시작 | 필요 시 문서 텍스트 추출 요청 |
| DOC-002 | GET | `/api/v1/career-documents` | 내 경력 문서 목록 | `documentType`, `status`, `page`, `size` | 문서 목록 | 현재 사용자의 문서만 조회 | 없음 |
| DOC-003 | GET | `/api/v1/career-documents/{documentId}` | 경력 문서 상세 조회 | `documentId` | 파일명, 종류, 상태, 생성일 | 소유권 확인 후 문서 메타데이터 제공 | 없음 |
| DOC-004 | DELETE | `/api/v1/career-documents/{documentId}` | 경력 문서 삭제 | `documentId` | 없음 | DB 기록과 저장 파일 삭제, 사용 중 문서 삭제 제한 | 없음 |
| DOC-005 | GET | `/api/v1/career-documents/{documentId}/analysis` | 면접용 이력서 구조화 결과 조회 | `documentId` | 경험·프로젝트·기술·품질 플래그·근거 참조 | 민감정보를 제외한 구조화 결과만 제공 | 이력서 분석 Agent |

`documentType`은 다음 두 값만 사용합니다.

- `RESUME`
- `COVER_LETTER`

지원공고는 `CAREER_DOCUMENTS`에 저장하지 않고 `JOB-001~005`로 관리합니다.

`DRAFT`, `IN_PROGRESS`, `INTERVIEW_COMPLETED`, `ANALYZING` 상태의 면접 세션이
이력서 또는 자기소개서를 참조하면 `DOC-004`는 `RESOURCE_IN_USE` 오류로
거부합니다. `COMPLETED`, `INTERRUPTED` 세션만 참조하는 문서는 기존 소프트
삭제와 Storage 삭제 정책에 따라 삭제할 수 있습니다.

### 4.3 지원공고

| ID | Method | URI | 기능 | Content-Type | 프론트 요청 | 주요 응답 | 백엔드 역할 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| JOB-001 | POST | `/api/v1/job-postings` | 지원공고 등록 | `multipart/form-data` | `inputType=FILE`, `targetJobRole`, `file` 필수 | `jobPostingId`, `processingStatus` | 사용자 제공 파일 검증·비공개 저장 후 비동기 추출·OCR·구조화 시작 |
| JOB-002 | GET | `/api/v1/job-postings` | 내 지원공고 목록 | 해당 없음 | `processingStatus`, `page`, `size` | 지원공고 목록 | 현재 사용자의 지원공고만 조회 |
| JOB-003 | GET | `/api/v1/job-postings/{jobPostingId}` | 지원공고 상세 조회 | 해당 없음 | `jobPostingId` | 원본 메타데이터, 추출·구조화 결과 | 소유권 확인 후 처리 상태와 지원정보 제공 |
| JOB-004 | PATCH | `/api/v1/job-postings/{jobPostingId}` | 지원공고 구조화 정보 수정 | `application/json` | 회사·직무·공고 항목 | 수정된 지원정보 | AI 추출 결과 또는 직접 입력값을 사용자 확인값으로 수정 |
| JOB-005 | DELETE | `/api/v1/job-postings/{jobPostingId}` | 지원공고 삭제 | 해당 없음 | `jobPostingId` | 없음 | DB 소프트 삭제와 FILE 원본 영구 삭제; Storage 실패 시 DB 복구 |

#### 허용 파일

| 구분 | 허용 확장자 | 처리 기준 |
| --- | --- | --- |
| 스크린샷 이미지 | JPG, JPEG, PNG | OCR로 텍스트를 추출한 뒤 지원정보 구조화 |
| 공고문 파일 | PDF | 텍스트 레이어 추출 후 부족한 페이지는 OCR, 지원정보 구조화 |

지원공고는 사용자 제공 `multipart/form-data` FILE만 받으며 `inputType=FILE`, `targetJobRole: AiJobRole`, `file`가 모두 필수입니다. 일반 텍스트, URL, 스크립트, DOCX, HWP는 받지 않습니다.

URL 및 `SCRIPT` 입력은 받지 않습니다. 업로드된 파일에 HTML·JavaScript·매크로·명령문 등이 포함되어도 서버에서 실행하지 않습니다.

#### JOB-001 FILE 요청 예시

```text
Content-Type: multipart/form-data

inputType: FILE
targetJobRole: AI_ENGINEER
file: 지원공고 스크린샷 또는 공고문 파일
```

허용 확장자는 PDF, JPG, JPEG, PNG이며 지원공고 한 건당 파일 한 개를 업로드합니다. 최대 파일 크기는 10MB, PDF 최대 페이지 수는 50, 이미지 최대 총 픽셀 수는 40MP입니다. 암호화·손상 PDF와 확장자 위장 파일은 거부합니다.

#### JOB-004 수정 가능 필드

필수 확인 항목:

- `companyName`
- `targetJobRole` (`AiJobRole`만 허용)
- `mainResponsibilities`
- `qualifications`

선택 항목:

- `preferredQualifications`
- `technologiesTools`
- `coreCompetencies`
- `companyBusinessIntro`

지원공고 등록 직후에는 구조화 필드가 비어 있을 수 있습니다. 면접 세션을 생성하기 전에는 처리 상태가 `READY`이고 네 개의 필수 확인 항목이 모두 존재해야 합니다.

`DRAFT`, `IN_PROGRESS`, `INTERVIEW_COMPLETED`, `ANALYZING` 상태의 면접 세션이
지원공고를 참조하면 `JOB-005`는 `RESOURCE_IN_USE` 오류로 거부합니다.
`COMPLETED`, `INTERRUPTED` 세션만 참조하는 공고는 삭제할 수 있으며, 삭제
후에도 세션에 저장된 지원정보 스냅샷은 유지됩니다.

### 4.4 면접 설정·진행

| ID | Method | URI | 기능 | 프론트 요청 | 주요 응답 | 백엔드 역할 | AI 연동 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SESSION-001 | POST | `/api/v1/interview-sessions` | 면접 세션 생성 | `resumeDocumentId`, `coverLetterDocumentId` 선택, `jobPostingId`, `persona`, `difficulty` | `sessionId`, `status=DRAFT` | 문서·공고 소유권과 준비 상태 검증, 지원정보 스냅샷 저장 | 없음 |
| SESSION-002 | GET | `/api/v1/interview-sessions/{sessionId}` | 면접 세션 조회 | `sessionId` | 설정, 지원정보 스냅샷, 진행 상태, 현재 질문 순서 | 본인 세션인지 확인 후 현재 상태 제공 | 없음 |
| SESSION-003 | PATCH | `/api/v1/interview-sessions/{sessionId}` | 면접 설정 수정 | 변경할 문서·공고·면접관·난이도 | 수정된 설정 | `DRAFT` 상태에서만 설정 수정, 공고 변경 시 스냅샷 갱신 | 없음 |
| SESSION-004 | POST | `/api/v1/interview-sessions/{sessionId}/start` | 면접 시작 | Header `Idempotency-Key`, `sessionId` | `202`, `sessionStatus=DRAFT`, `questionGenerationStatus=QUEUED`, `currentQuestion=null` | 시작 조건 확인, 질문 생성·첫 캐릭터 미디어 작업을 멱등적으로 등록 | 기본 질문 5개 생성 후 첫 질문 TTS·MuseTalk 요청 |
| SESSION-005 | POST | `/api/v1/interview-sessions/{sessionId}/completion` | 면접 종료·중단 | Header `Idempotency-Key`, `completionType` | `NORMAL`은 `INTERVIEW_COMPLETED`, `USER_INTERRUPTED`는 `INTERRUPTED` | 답변 수집 완료 또는 사용자 중단을 멱등적으로 확정 | 이번 단계에서는 최종 분석 작업을 등록하지 않음 |
| QUESTION-001 | GET | `/api/v1/interview-sessions/{sessionId}/questions/current` | 현재 질문 조회 | `sessionId` | 생성·미디어 준비 중 `202`, 질문 또는 전체 답변 완료 상태 `200` | 세션과 Turn 상태로 현재 질문 결정 | TTS·MuseTalk 준비 상태 반영 |
| QUESTION-002 | POST | `/api/v1/interview-sessions/{sessionId}/questions/{questionId}/character-media-access` | 질문 캐릭터 영상 재생 권한 발급 | `sessionId`, `questionId` | `200 PlaybackAccess`, 준비 중 `202`, 폴백 `409` | 소유권·현재 질문·미디어 상태 검증 후 짧은 재생 권한 발급 | 없음 |
| ANSWER-003 | POST | `/api/v1/interview-answers/{answerId}/media-access` | 답변 근거 구간 재생 권한 발급 | `answerId`, `startMs`, `endMs` | `200 PlaybackAccess` | 답변 소유권·근거 구간 검증 후 짧은 재생 권한 발급 | 없음 |
| MEDIA-003 | GET | `/media/v1/playback/{playbackToken}` | 브라우저 MP4 재생 | `playbackToken`, `Range` 선택 | `200/206 video/mp4` | opaque token 검증 뒤 private media Range streaming | 없음 |

`SESSION-001`은 별도 언어 값을 받지 않습니다. 한국어 면접과 한국어 STT를 기본으로 사용합니다.

`SESSION-001~003`은 `AUTH-003` 또는 `AUTH-004`에서 발급한 정상 access token으로 인증된 `ACTIVE` 회원이면서
온보딩 상태가 `COMPLETED`일 때만 사용할 수 있습니다. 이력서는 필수,
자기소개서는 선택이며 현재 회원 소유의 삭제되지 않은 `READY` 문서만
지정할 수 있습니다. 지원공고도 현재 회원 소유의 삭제되지 않은 `READY`
리소스여야 하고 `companyName`, `targetJobRole`, `mainResponsibilities`,
`qualifications`가 모두 채워져 있어야 합니다.

지원공고의 다음 구조화 정보 8개는 면접 세션 생성 시점에 세션 스냅샷으로
복사합니다.

- 필수: `companyName`, `targetJobRole`, `mainResponsibilities`, `qualifications`
- 선택: `preferredQualifications`, `technologiesTools`, `coreCompetencies`,
  `companyBusinessIntro`

이후 원본 지원공고가 수정되거나 삭제되어도 기존 세션의 기준 데이터는
변경하지 않습니다. `SESSION-003`에서 `jobPostingId`를 실제로 변경할 때만
새 공고의 8개 값으로 스냅샷 전체를 원자적으로 교체합니다.

`SESSION-003`은 `DRAFT` 상태에서만 사용할 수 있습니다. 수정 가능 필드는
`resumeDocumentId`, `coverLetterDocumentId`, `jobPostingId`, `persona`,
`difficulty`이며 `coverLetterDocumentId`만 명시적 `null`로 연결을 해제할
수 있습니다. 빈 PATCH, 알 수 없는 필드, 나머지 필수 필드의 명시적
`null`은 거부합니다.

`persona`는 `TECHNICAL`, `HR`, `EXECUTIVE`만 허용합니다. `difficulty`는
`GENERAL`, `PRESSURE`만 허용합니다. 다른 값, 빈 값, `null`은 거부합니다.

세션 상태는 `DRAFT`, `IN_PROGRESS`, `INTERVIEW_COMPLETED`, `ANALYZING`,
`COMPLETED`, `INTERRUPTED`만 사용합니다. 신규 세션은 `DRAFT`이고
`currentTurnOrder`는 `null`입니다.

`SESSION-004`는 질문 생성 작업을 `QUEUED`로 등록하고 `202 Accepted`를
반환합니다. 질문 생성 중에는 세션을 `DRAFT`로 유지하고 `startedAt`을
기록하지 않습니다. Worker가 검증된 기본 질문 5개를 모두 저장한 트랜잭션에서만
세션을 `IN_PROGRESS`로 전환하고 `startedAt`과
`currentTurnOrder=1`을 기록합니다. 질문 생성이 실패하면 세션은
`DRAFT`로 유지합니다.

MVP는 기본 질문 5개와 각 기본 질문 답변 기반 꼬리 질문 0~1개를 생성합니다.
기본 질문 순서는 1부터 5까지 연속이며 자기소개·지원동기 1개,
이력서·경험 1개, 직무·채용공고 1개, 상황·행동·협업 1개,
마무리·성장계획 1개로 구성합니다. 꼬리 질문은 직전 기본 질문의 답변에서
확인이 필요한 구체성·근거·역할·성과가 있을 때만 생성합니다.

- 기본 질문 하나당 꼬리 질문 최대 1개
- 꼬리 질문에 대한 추가 꼬리 질문 금지
- 총 turn 수 5~10개
- `GENERAL`은 명확성 보완 중심, `PRESSURE`는 판단 근거 검증 빈도를 높임
- 공격·모욕·보호 특성·불필요한 개인정보 질문 금지
- 꼬리 질문 생성 실패 시 해당 질문을 건너뛰고 다음 기본 질문 진행

`completionType`은 다음 두 값만 사용합니다.

- `NORMAL`: 기본 질문 5개와 실제 생성된 모든 꼬리 질문의 답변 미디어가
  확정되고 마지막 꼬리 질문 결정까지 완료된 경우
  `IN_PROGRESS → INTERVIEW_COMPLETED`
- `USER_INTERRUPTED`: 미답변 질문이 있어도
  `IN_PROGRESS → INTERRUPTED`

`SESSION-005` 응답 트랜잭션은 `INTERVIEW_COMPLETED`까지만 전환합니다.
커밋 후 분석 조정 Worker가 필수 답변과 작업을 재검증해 `ANALYZING`으로
전환하며, 리포트 확정 트랜잭션에서만 `COMPLETED`가 됩니다. 개별 답변
분석의 성공 여부는 `NORMAL` 종료 조건과 분리합니다.

### 4.5 답변 제출·처리

| ID | Method | URI | 기능 | 프론트 요청 | 주요 응답 | 백엔드 역할 | AI 연동 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER-001 | POST | `/api/v1/interview-sessions/{sessionId}/answers` | 답변 클립 제출 | Header `Idempotency-Key`, `questionId`, `file`, `recordedDurationMs`, `endedBy` | `answerId`, `answerStatus`, `nextQuestionStatus` | MP4·WebM 검증·비공개 저장, 질문과 답변 연결, 중복 제출 방지 | STT·CV·내용 분석 작업 등록, 세션의 음성 분석 동의 시에만 VOICE 추가 |
| ANSWER-002 | GET | `/api/v1/interview-answers/{answerId}` | 답변 처리 상태 조회 | `answerId` | 처리 상태, 단계별 작업 상태, 다음 질문 준비 여부 | 본인 답변 확인, AI 처리 결과와 다음 질문 상태 제공 | 없음 |
| ANSWER-003 | POST | `/api/v1/interview-answers/{answerId}/media-access` | 답변 근거 구간 재생 권한 발급 | `startMs`, `endMs` | `PlaybackAccess` | 소유권·근거 범위 검증 | 없음 |

`endedBy` 값은 다음과 같습니다.

- `USER_BUTTON`: 답변 완료 버튼
- `SPACE_KEY`: Space 단축키
- `SILENCE_CONFIRMED`: 3초 이상 답변 후 2초 무음, 1초 카운트다운 동안 추가 발화 없음

VAD는 프론트의 녹음 제어 정책입니다. 발화 시작 후 첫 3초에는 무음 종료를 판정하지 않습니다. 이후 연속 2초 무음이면 `SILENCE_CANDIDATE`를 표시하고 1초 카운트다운을 시작합니다. 카운트다운 중 발화가 재개되면 즉시 취소합니다. 답변 완료 버튼과 Space는 모든 단계에서 즉시 사용 가능하며, 동일 `questionId`의 완료 요청은 `Idempotency-Key`로 한 번만 저장합니다.

침묵 감지는 프론트엔드에서 수행하고 백엔드는 검증 가능한 종료 결과만 받습니다.

답변은 영상과 음성 스트림이 모두 있는 MP4(`video/mp4`, ISO BMFF
`ftyp`) 또는 WebM(`video/webm`, EBML `1A 45 DF A3`)만 허용합니다.
최대 크기는 200MB, 최대 녹화 길이는 300초입니다. 요청 MIME만 신뢰하지
않고 컨테이너 시그니처·구조·스트림·길이를 교차 검증하며 위반 시
`400 INVALID_ANSWER_MEDIA`를 반환합니다.

원본은 공개 접근이 차단된 `interview-answers` bucket에
`sessions/{sessionUuid}/turns/{turnUuid}/{answerUuid}.{extension}` 형태로
저장합니다. bucket과 object key는 API 응답이나 로그에 노출하지 않습니다.

`SESSION-004`, `ANSWER-001`, `SESSION-005`에는 8~64자의
`Idempotency-Key`가 필수입니다. 영문·숫자·`.`, `_`, `:`, `-`만
허용하며 범위는 `memberId + HTTP method + URI + Idempotency-Key`입니다.
같은 키·같은 요청은 최초 HTTP 상태와 응답을 재사용하고, 요청 내용이 다르면
`409 IDEMPOTENCY_KEY_REUSED`, 처리 중이면
`409 IDEMPOTENCY_REQUEST_IN_PROGRESS`를 반환합니다. 하나의 Turn에는
하나의 확정 답변만 허용하며 다른 키로 다시 제출하면
`409 ANSWER_ALREADY_SUBMITTED`를 반환합니다.

#### ANSWER-001 요청 예시

```text
Content-Type: multipart/form-data

questionId: 질문 UUID
file: 답변 영상 또는 음성 포함 영상
recordedDurationMs: 72000
endedBy: USER_BUTTON
```

#### ANSWER-002 주요 응답 예시

```json
{
  "answerId": "answer-uuid",
  "status": "PROCESSING",
  "followUpDecisionStatus": "PROCESSING",
  "nextQuestionStatus": "WAITING",
  "nextQuestionId": null,
  "processingSteps": []
}
```

STT 전문은 CONTENT 내부 입력으로만 사용하며 `ANSWER-002`, 분석 상태 및
리포트 응답에 포함하지 않습니다.

### 4.6 분석·리포트·마이페이지

| ID | Method | URI | 기능 | 프론트 요청 | 주요 응답 | 백엔드 역할 | AI 연동 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ANALYSIS-001 | GET | `/api/v1/interview-sessions/{sessionId}/analysis-status` | 분석 진행 상태 조회 | `sessionId` | 전체 상태, 단계별 상태, 진행률, 실패 단계 | 여러 AI 작업 상태를 한 화면용 상태로 통합 | 없음 |
| REPORT-001 | GET | `/api/v1/interview-sessions/{sessionId}/report` | 면접 종합 리포트 조회 | `sessionId` | 종합 점수, 음성 동의에 따른 3개 또는 4개 축 결과, 강점·개선 항목, 질문별 공개 피드백 | Worker가 확정 저장한 리포트 제공 | 없음 |
| HISTORY-001 | GET | `/api/v1/members/me/interview-sessions` | 내 면접 이력 조회 | `status`, `page`, `size` | 기업, 직무, 완료일, 점수, 리포트 ID | 현재 사용자의 면접 목록 제공 | 없음 |
| GROWTH-001 | GET | `/api/v1/members/me/growth` | 회차별 성장 추이 조회 | `limit`, `from`, `to` | 회차별 종합·평가 축 점수 | 완료된 리포트 점수를 시간순으로 집계 | 없음 |

#### 분석 상태 응답 예시

```json
{
  "sessionId": "session-uuid",
  "sessionStatus": "ANALYZING",
  "analysisStatus": "PROCESSING",
  "totalAnswerCount": 7,
  "completedAnswerCount": 4,
  "failedAnswerCount": 0,
  "totalRequiredTaskCount": 28,
  "succeededRequiredTaskCount": 22,
  "progressPercent": 78.6,
  "stages": {
    "stt": { "total": 7, "queued": 0, "processing": 1, "succeeded": 6, "failed": 0 },
    "cv": { "total": 7, "queued": 1, "processing": 1, "succeeded": 5, "failed": 0 },
    "voice": { "total": 7, "queued": 0, "processing": 0, "succeeded": 7, "failed": 0 },
    "content": { "total": 7, "queued": 3, "processing": 0, "succeeded": 4, "failed": 0 }
  },
  "reportStatus": "WAITING_FOR_ANALYSIS",
  "retryable": false
}
```

#### 리포트 응답 주요 구조

```json
{
  "sessionId": "session-uuid",
  "sessionStatus": "COMPLETED",
  "reportStatus": "SUCCEEDED",
  "report": {
    "reportId": "report-uuid",
    "schemaVersion": "1.0",
    "overallScore": 82.4,
    "scores": {
      "gaze": 81.2,
      "posture": 78.5,
      "speech": 84.8,
      "content": 85.1
    },
    "strengths": [],
    "improvements": [],
    "questionFeedback": [],
    "generatedAt": "2026-07-30T10:00:00+09:00"
  }
}
```

`ANALYSIS-001`의 분석 상태는 `WAITING`, `PROCESSING`, `SUCCEEDED`, `FAILED`입니다.
전체 필수 작업 수는 음성 분석 동의 시 답변 수×4, 미동의 시 답변 수×3입니다. 10개 답변 기준 각각 40개와 30개입니다.
진행률은 성공한 필수 작업 수를 전체 필수 작업 수로 나눕니다. 실패 작업은
성공 진행률로 계산하지 않습니다. 분석 최종 실패도 HTTP 200으로 조회하되
`ANSWER_ANALYSIS_FAILED`와 `BLOCKED_BY_ANALYSIS_FAILURE`만 노출합니다.

`REPORT-001`은 조회 중 리포트를 생성하지 않습니다. 분석 대기·리포트 생성 중에는 HTTP 202, 완료된 리포트는 HTTP 200, 분석 실패 차단은 `409 REPORT_BLOCKED_BY_ANALYSIS_FAILURE`, 리포트 생성 최종 실패는 `503 REPORT_GENERATION_FAILED`, 중단 세션은 `409 REPORT_NOT_AVAILABLE`입니다.

정상 종료 세션은 `INTERVIEW_COMPLETED → ANALYZING → COMPLETED`로 전환합니다. CONTENT는 같은 답변의 STT 성공 후에만 실행하며 STT 최종 실패 시 외부 호출 없이 `DEPENDENCY_FAILED`가 됩니다. 모든 답변의 STT·CV·CONTENT와, 음성 분석 동의 세션의 VOICE가 성공한 뒤에만 세션당 단일 `REPORT_GENERATION` 작업을 등록합니다.

리포트 축은 CV 시선=`GAZE`, CV 자세=`POSTURE`, VOICE 말하기=`SPEECH`,
CONTENT 답변 내용=`CONTENT`입니다. 각 축은 기본 질문과 실제 생성된
꼬리 질문의 모든 확정 답변 산술평균입니다. 음성 분석 미동의 시
`SPEECH`는 `null`이며 종합 점수는 나머지 세 축만 동일 가중치로 계산합니다.
동의 시 종합은 네 축 동일 가중치 평균이며 모두 `HALF_UP`으로 소수점 첫째 자리까지 확정 저장합니다.
부분 리포트와 누락 점수의 0점 대체는 허용하지 않습니다.

분석 결과·질문별 공개 피드백은 `REPORT-001`에 포함하지만 전체 STT, 문서·공고 원문, 외부 원본 응답, Storage 위치와 Worker token은 포함하지 않습니다.

### 4.7 음성 클론 — V1 제외·후속 선택 기능

| ID | Method | URI | 기능 | 프론트 요청 | 주요 응답 | 백엔드 역할 | AI 연동 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| VOICE-001 | POST | `/api/v1/voice-profiles` | 음성 클론 프로필 등록 | `consentLegalRecordId`, 샘플 파일 | `voiceProfileId`, `voiceStatus=QUEUED` | 별도 음성 동의 확인, 샘플 검증·저장, 중복 생성 방지 | 음성 복제 모델 생성 요청 |
| VOICE-002 | GET | `/api/v1/voice-profiles/me` | 내 음성 프로필 조회 | 없음 | 프로필 상태, 사용 가능 여부 | 현재 사용자의 프로필 상태 제공 | 없음 |
| VOICE-003 | DELETE | `/api/v1/voice-profiles/me` | 음성 프로필 삭제 | 없음 | 없음 | 샘플·미리듣기·모델 참조 삭제 절차 시작 | AI 측 복제 모델 삭제 요청 |

#### 음성 클론 구현 기준

- 음성정보 동의는 온보딩 필수 동의에 포함하지 않습니다.
- `VOICE-001` 호출 전에 현재 사용자의 유효한 음성정보 동의 기록이 있어야 합니다.
- 샘플 파일과 복제 모델은 현재 사용자에게만 귀속됩니다.
- 동일 사용자는 삭제되지 않은 음성 프로필을 하나만 보유하는 것을 기본으로 합니다.
- 복제 작업은 비동기로 처리하며 등록 직후 `QUEUED`를 반환합니다.
- `VOICE-002`는 `QUEUED`, `PROCESSING`, `READY`, `FAILED`, `DELETING` 상태를 제공합니다.
- `READY`가 되기 전에는 해당 복제 음성을 사용할 수 없습니다.
- 외부 AI 모델 식별자는 프론트엔드에 직접 노출하지 않습니다.
- `VOICE-003`은 DB 행만 삭제하는 것으로 끝내지 않고 저장 파일과 외부 AI 모델 삭제까지 추적합니다.
- 동의 철회 시 기존 음성 프로필의 사용 중지와 삭제 절차가 필요합니다.

#### VOICE-001 요청 예시

```text
Content-Type: multipart/form-data

consentLegalRecordId: 음성정보 동의 기록 UUID
file: 사용자 음성 샘플 파일
```

#### VOICE-001 주요 응답 예시

```json
{
  "voiceProfileId": "voice-profile-uuid",
  "voiceStatus": "QUEUED",
  "usable": false
}
```

#### VOICE-002 주요 응답 예시

```json
{
  "voiceProfileId": "voice-profile-uuid",
  "voiceStatus": "READY",
  "usable": true,
  "createdAt": "2026-07-28T10:30:00+09:00",
  "completedAt": "2026-07-28T10:31:20+09:00"
}
```

음성 클론 생성 후 개선 답변 음성 재생은 `AUDIO-001`을 사용합니다. AI 내부
합성 방식과 외부 model 식별자는 공개 계약에 포함하지 않습니다.

### 4.8 통합 보완 API

| ID | Method | URI | 기능 |
| --- | --- | --- | --- |
| LEGAL-003 | POST | `/api/v1/legal-consents` | 기능별 동의 기록 생성 |
| LEGAL-004 | DELETE | `/api/v1/legal-consents/{consentRecordId}` | 기능별 동의 철회 |
| MEMBER-002 | DELETE | `/api/v1/members/me` | 회원 탈퇴·전체 삭제 시작 |
| MEMBER-003 | GET | `/api/v1/members/me/deletion` | 회원 삭제 상태 조회 |
| SESSION-006 | POST | `/api/v1/interview-sessions/{sessionId}/clone` | 재연습 세션 복제 |
| QUESTION-002 | POST | `/api/v1/interview-sessions/{sessionId}/questions/{questionId}/character-media-access` | TTS+MuseTalk 질문 캐릭터 영상 재생 권한 발급 |
| ANSWER-003 | POST | `/api/v1/interview-answers/{answerId}/media-access` | 답변 근거 구간 재생 권한 발급 |
| MEDIA-003 | GET | `/media/v1/playback/{playbackToken}` | 브라우저 MP4 재생 |
| ANALYSIS-002 | POST | `/api/v1/interview-sessions/{sessionId}/analysis-retry` | 실패 분석 재시도 |
| MEDIA-001 | DELETE | `/api/v1/interview-sessions/{sessionId}/media` | 원본 면접 미디어 삭제 |
| MEDIA-002 | GET | `/api/v1/interview-sessions/{sessionId}/media-deletion` | 미디어 삭제 상태 조회 |
| AUDIO-001 | GET | `/api/v1/reports/{reportId}/question-feedback/{feedbackId}/improved-answer-audio` | 개선 답변 음성 재생 |
| TELEMETRY-001 | POST | `/api/v1/client-events` | 민감 원문 없는 클라이언트 이벤트 |
| CONTEXT-001 | GET | `/api/v1/interview-sessions/{sessionId}/question-context` | 질문 생성 근거·RAG source 요약 조회 |
| DOC-005 | GET | `/api/v1/career-documents/{documentId}/analysis` | 이력서·자기소개서 면접용 구조화 결과 조회 |

상세 요청·응답과 MuseTalk 캐릭터 미디어 계약은 12절을 따릅니다.

## 5. 지원공고 입력·처리 흐름

### 5.1 필수 FILE 입력과 비동기 처리

```text
JOB-001 필수 FILE 검증
→ FILE이면 확장자·MIME 타입·실제 파일 형식 검증 후 Private Storage 저장
→ processingStatus=PROCESSING
→ 트랜잭션 커밋 후 백그라운드 Worker 실행
→ 캡처 이미지이면 Tesseract OCR, PDF이면 텍스트 추출·부족 페이지 OCR
→ 지원정보 구조화
→ 필수 구조화 필드가 모두 있으면 READY, 아니면 FAILED
→ JOB-003 결과 조회
→ 필요한 경우 JOB-004로 사용자 수정
→ SESSION-001에서 jobPostingId 사용
```

### 5.2 보안 기준

- 업로드된 지원공고 파일은 공개 URL로 노출하지 않습니다.
- 확장자만 믿지 않고 MIME 타입과 실제 파일 형식을 검증합니다.
- 지원공고 FILE 원본은 10MB 이하만 `job-postings` Private bucket에 저장하며 공개 URL이나 signed URL을 발급하지 않습니다.
- HWP 5.x는 OLE2/CFB·FileHeader·문서 버전·암호화·배포용 상태를 검증하고, 별도 JVM에서 메모리·시간·출력 길이를 제한해 파싱합니다.
- 업로드 파일에 HTML·JavaScript·매크로·명령문이 포함되어도 실행하지 않습니다.
- TEXT 입력도 일반 문자열로만 저장·구조화하며 코드나 명령으로 실행하지 않습니다.
- 원본 파일명이나 사용자 경로는 Storage 객체 키 및 임시 파일명으로 사용하지 않습니다.
- 원본, 전체 추출 텍스트, Supabase Secret Key는 로그에 기록하지 않습니다.
- 프론트 출력 시 HTML 이스케이프 또는 안전한 텍스트 렌더링을 적용합니다.
- 원본 파일·추출 텍스트·구조화 결과는 등록한 회원만 접근할 수 있습니다.
- 면접 세션에서 사용 중인 지원공고의 삭제 허용 방식은 구현 전에 확정합니다.

### 5.3 Storage·처리·검증 기준

- FILE 원본은 `job-postings` Private bucket에 저장합니다.
- Storage 허용 MIME은 `application/pdf`, `image/jpeg`, `image/png`입니다.
- 객체 키는 `{verified-sub}/{jobPostingId}/{server-uuid}.{validated-extension}` 형식이며 upsert하지 않습니다.
- PDF 텍스트 레이어는 PDFBox로 추출하고 텍스트가 부족한 페이지만 300 DPI 이미지로 렌더링해 OCR합니다.
- JPG·JPEG·PNG는 실제 디코딩과 40MP 제한을 적용하고 EXIF 방향을 보정한 뒤 OCR합니다.
- Tesseract는 `kor+eng`을 기본으로 하며 명령과 인수를 분리하고 제한시간 및 임시 파일 정리를 적용합니다.
- 추출·OCR 결과는 50,000자를 넘지 않으며 원문과 전체 추출 결과를 로그에 남기지 않습니다.
- 기존 및 신규 자동 테스트는 실제 최소 유효 PDF·JPG·PNG fixture와 손상·위장 파일 fixture를 사용하며 Tesseract 미설치 환경에서도 Skip 없이 실행되어야 합니다.

### 5.4 제외 범위와 완료 기준

DOCX·HWP·HWPX, 일반 텍스트·URL·스크립트 입력, 암호화·비밀번호 보호·손상 PDF, 외부 OCR·LLM·크롤링·스크래핑·파일 공개 URL·signed URL·다운로드 API는 제외합니다.

완료 기준은 ACTIVE 및 온보딩 완료 회원이 필수 지원공고 FILE(PDF 또는 캡처 이미지)을 등록하고, 커밋 후 비동기 추출·OCR·결정적 구조화를 거쳐 `READY` 또는 `FAILED` 상태를 확인·보완하며, 본인 공고만 조회·수정·삭제할 수 있는 것입니다. FILE 삭제 시 DB 소프트 삭제와 Storage 원본 영구 삭제를 함께 처리합니다.

## 6. 백엔드와 AI 서버의 내부 연동 경계

AI 모델이 어떻게 분석하는지는 AI 담당자가 결정합니다. 백엔드는 입력을 전달하고 작업 상태와 결과를 받아 저장합니다.

| 내부 기능 | 호출 시점 | 백엔드가 전달할 값 | 백엔드가 받아야 할 값 | 백엔드 후속 처리 |
| --- | --- | --- | --- | --- |
| 경력 문서 처리 | DOC-001 등록 후 | `documentId`, 파일 참조, 문서 종류 | 추출 텍스트, 처리 상태, 오류 | 문서 상태와 추출 결과 저장 |
| 지원공고 처리 | JOB-001 등록 후 | `jobPostingId`, 비공개 파일 참조, 검증된 파일 형식 | 추출 텍스트, 구조화 필드, 처리 상태, 오류 | 지원공고 처리 상태와 구조화 결과 저장 |
| 질문 생성 | 면접 시작·답변 처리 후 | 세션 스냅샷, 문서 텍스트, 이전 질문·답변 | 질문 내용, 질문 유형, 부모 질문 ID | 질문 순서와 현재 질문 저장 |
| 질문 캐릭터 미디어 | 질문 저장 후 | `questionId`, 질문 텍스트, 면접관 캐릭터 자산 | TTS 음성, MuseTalk MP4, 길이·상태·오류 | 비공개 저장 후 질문 미디어 상태 갱신; 실패 시 정적 캐릭터+텍스트 폴백 |
| STT | 답변 업로드 후 | `answerId`, 미디어 참조 | 한국어 전사문, 시간 정보, 처리 상태 | 답변에 전사 결과 연결 |
| CV 분석 | 답변 업로드 또는 면접 종료 후 | `answerId`, 영상 참조 | 시선·자세 측정값, 처리 상태 | 답변별 분석 결과 저장 |
| 발화·내용 분석 | STT 완료 후 | 질문, 전사문, 답변 시간, 문서·지원공고 맥락 | 발화 지표, 내용 점수, 근거, 개선안 | 답변별 점수와 피드백 저장 |
| 리포트 생성 | 모든 필수 분석 완료 후 | 정규화된 질문별 3개 또는 4개 축 점수와 공개 피드백 | 외부 호출 없음 | 결정적 집계, 최종 리포트 저장과 세션 `COMPLETED` 전환 |
| 음성 클론 생성 | VOICE-001 샘플 등록 후 | `voiceProfileId`, 비공개 샘플 참조, 동의 확인 결과 | 외부 모델 참조, 미리듣기 참조, 처리 상태, 오류 | 음성 프로필 상태와 모델 참조 저장 |
| 음성 클론 삭제 | VOICE-003 삭제 요청 후 | `voiceProfileId`, 외부 모델 참조 | 삭제 상태, 오류 | 외부 모델·샘플·미리듣기 삭제 상태 반영 |

### 6.1 내부 연동 공통 식별값

- `jobId`: AI 작업 식별자
- `memberId`: 소유 회원 식별자
- `documentId`: 경력 문서 식별자
- `jobPostingId`: 지원공고 식별자
- `sessionId`: 면접 세션 식별자
- `questionId`: 질문 식별자
- `answerId`: 답변 식별자
- `mediaFileId`: 백엔드가 관리하는 파일 식별자
- `voiceProfileId`: 음성 클론 프로필 식별자
- `requestedAt`: 작업 요청 시각

AI 서버는 데이터베이스에 직접 접근하지 않습니다. 백엔드가 전달한 파일 참조와 최소 데이터만 사용하며 결과에는 반드시 `jobId`와 대상 ID가 포함되어야 합니다.

### 6.2 백엔드 ↔ AI 서버 실제 HTTP 계약

공개 API와 내부 worker 계약은 분리한다. 백엔드는 `POST {AI_INTERNAL_BASE_URL}/v1/jobs`로 작업을 등록하고, AI 서버는 즉시 `202 {jobId,acceptedAt}`를 반환한다. 두 방향 모두 service JWT와 `X-Request-Id`, `Idempotency-Key`를 사용한다. AI callback은 추가로 `X-Job-Signature`(timestamp 포함 HMAC)를 검증한다.

```ts
type AiJobRequest = {
  schemaVersion: "1.0";
  jobId: string;
  jobType: "DOCUMENT_PARSE" | "JOB_POSTING_PARSE" | "QUESTION_PLAN"
    | "FOLLOW_UP_DECISION" | "CHARACTER_MEDIA_RENDER" | "ANSWER_ANALYSIS" | "REPORT_GENERATE";
  requestedAt: string;
  traceId: string;
  callbackUrl: string;
  payload: Record<string, unknown>;
};

type AiJobCallback = {
  schemaVersion: "1.0";
  jobId: string;
  resultRevision: number;
  status: "SUCCEEDED" | "FAILED";
  completedAt: string;
  result: Record<string, unknown> | null;
  error: { code: "AI_INPUT_INVALID" | "AI_PROVIDER_UNAVAILABLE" | "AI_TIMEOUT" | "AI_OUTPUT_INVALID" | "AI_SAFETY_BLOCKED"; retryable: boolean; stage: string } | null;
};
```

AI 서버 callback URI는 `POST /internal/v1/ai-jobs/{jobId}/result`다. 백엔드는 `jobId + resultRevision`으로 callback을 멱등 처리하고, 더 낮은 revision 또는 중복 결과를 무시한다. AI 서버는 프론트 API, DB, 외부 URL을 직접 호출하지 않는다. 파일이 필요하면 백엔드가 `mediaFileId`별 내부 전용·짧은 수명의 download URL을 payload에 넣는다.

| `jobType` | 백엔드 → AI `payload` 최소값 | AI → 백엔드 `result` 최소값 |
| --- | --- | --- |
| `DOCUMENT_PARSE` | `documentId`, `mediaFileId`, `documentType` | `extractedText`, `sections`, `confidence` |
| `JOB_POSTING_PARSE` | `jobPostingId`, `mediaFileId`, `targetJobRole` | `companyName`, `mainResponsibilities`, `qualifications`, `targetJobRole` |
| `QUESTION_PLAN` | `sessionId`, `jobPostingSnapshot`, `resumeProfile`, `persona`, `difficulty` | base questions 5개, evidence refs, validation result |
| `FOLLOW_UP_DECISION` | `sessionId`, `questionId`, `answerId`, `fastTranscript`, `jobPostingSnapshot` | `GENERATED` 질문 0~1개 또는 `SKIPPED`, reason |
| `CHARACTER_MEDIA_RENDER` | `sessionId`, `questionId`, `persona`, `questionText`, `characterAssetId` | `mediaFileId`, `durationMs`, `status=READY|FAILED_FALLBACK` |
| `ANSWER_ANALYSIS` | `sessionId`, `answerId`, `questionId`, `mediaFileId`, `mediaDurationMs` | STT·CV·CONTENT 및 동의 세션의 VOICE 단계 결과와 시간 근거 |
| `REPORT_GENERATE` | `sessionId`, 분석 결과, rubric version | report, question feedback, 시간 근거 |

내부 오류는 공개 오류로 직접 노출하지 않는다. 작업 상태는 `FAILED`와 실패 단계에 저장하며, 동기 호출 불가만 `502 AI_SERVICE_ERROR`로 반환한다.

## 7. 오류 코드 단일 등록부

모든 JSON 오류는 `{error:{code,message,requestId,retryable}}` 형식이며, 아래 표 외 `code`를 프론트 계약에 추가하지 않는다.

| HTTP | 코드 | 프론트 분류·행동 | 재시도 |
| --- | --- | --- | --- |
| 400 | `VALIDATION_FAILED`, `INVALID_IDEMPOTENCY_KEY` | 입력 필드 오류 표시 | 아니오 |
| 400 | `INVALID_ANSWER_MEDIA`, `INVALID_VOICE_SAMPLE`, `PLAYBACK_RANGE_INVALID` | 녹화/근거 범위 다시 선택 | 아니오 |
| 400 | `ROLE_NOT_SUPPORTED` | AI 직무만 선택 가능 안내 | 아니오 |
| 400 | `IDEMPOTENCY_KEY_REQUIRED` | 클라이언트 오류 보고, 현재 입력 유지 | 아니오 |
| 401 | `AUTH_REQUIRED`, `PLAYBACK_ACCESS_EXPIRED` | 로그인 또는 재생 권한 재발급 | 예 |
| 403 | `ACCESS_DENIED`, `ONBOARDING_REQUIRED`, `VOICE_CONSENT_REQUIRED` | 권한·온보딩·동의 화면 이동 | 아니오 |
| 404 | `RESOURCE_NOT_FOUND` | 목록으로 이동, 새로고침 | 아니오 |
| 409 | `INVALID_STATE`, `RESOURCE_NOT_READY`, `RESOURCE_IN_USE`, `VOICE_PROFILE_NOT_READY` | 현재 상태 설명 후 조회 갱신 | 조건부 |
| 409 | `DUPLICATE_REQUEST`, `IDEMPOTENCY_REQUEST_IN_PROGRESS` | 버튼 잠금 유지, 상태 조회 | 예 |
| 409 | `IDEMPOTENCY_KEY_REUSED`, `ANSWER_ALREADY_SUBMITTED` | 중복 제출 차단, 최신 상태 표시 | 아니오 |
| 409 | `INCOMPLETE_INTERVIEW`, `FOLLOW_UP_DECISION_IN_PROGRESS` | 면접 진행/대기 화면 유지 | 조건부 |
| 409 | `CHARACTER_MEDIA_UNAVAILABLE` | 정적 캐릭터+질문 텍스트로 폴백 | 아니오 |
| 413 | `FILE_TOO_LARGE` | 파일 변경 | 아니오 |
| 415 | `FILE_TYPE_NOT_SUPPORTED` | 지원 형식 안내 | 아니오 |
| 429 | `RATE_LIMITED` | `retryAfterSec` 뒤 재시도 | 예 |
| 500 | `INTERNAL_ERROR` | 입력 보존, 오류 안내 | 조건부 |
| 502 | `AI_SERVICE_ERROR` | 상태 조회로 전환 | 예 |
| 503 | `QUESTION_GENERATION_FAILED` | 검증된 AI 직무 템플릿 질문으로 계속 | 아니오 |

AI 처리 실패는 가능하면 API 전체 오류로 끝내지 않고 `FAILED` 상태와 실패 단계를 저장하여 프론트엔드가 상태 조회 화면에서 확인할 수 있게 합니다.
`AI_INPUT_INVALID`, `AI_PROVIDER_UNAVAILABLE`, `AI_TIMEOUT`, `AI_OUTPUT_INVALID`, `AI_SAFETY_BLOCKED`, `AGENT_BUDGET_EXCEEDED`는 §6.2 AI worker 내부 코드이며 공개 API `error.code`로 반환하지 않습니다. `ANSWER_ANALYSIS_FAILED`, `BLOCKED_BY_ANALYSIS_FAILURE`, `REPORT_GENERATION_FAILED`는 `AnalysisStatus.failureCode` 상태값입니다.

## 8. 프론트엔드 협업 기준

| 화면 | 프론트가 호출할 핵심 API | 프론트 표시 기준 |
| --- | --- | --- |
| 로그인 | AUTH-001~003, AUTH-006 | `memberStatus`, `onboardingStatus`, `nextAction` |
| 온보딩 | LEGAL-001~002, ONBOARDING-001 | 최신 필수 문서, 필요 행위, 완료 상태 |
| 문서 등록 | DOC-001~003 | 이력서·자기소개서 처리 상태 |
| 지원공고 등록 | JOB-001~004 | 허용 파일 형식, 처리 상태, 추출·구조화 결과 |
| 면접 설정 | DOC-002~003, JOB-002~004, SESSION-001~003 | 문서·지원공고 `READY`, 세션 `DRAFT` |
| 면접 진행 | SESSION-004, QUESTION-001~002, ANSWER-001~002 | 현재 질문, MuseTalk 캐릭터 영상, 답변 처리, 다음 질문 준비 여부 |
| 분석 중 | SESSION-005, ANALYSIS-001~002 | 분석 전체 상태, 단계별 상태, 실패 재시도 |
| 리포트 | REPORT-001, AUDIO-001 | `COMPLETED` 리포트와 개선 답변 음성 |
| 마이페이지 | MEMBER-001, HISTORY-001, GROWTH-001 | 프로필, 면접 목록, 회차별 점수 |
| 동의·삭제 | LEGAL-003~004, MEDIA-001~002, MEMBER-002~003 | 기능 동의, 철회, 미디어·회원 삭제 상태 |
| 음성 클론 | LEGAL-001~004, VOICE-001~003 | 별도 동의, 샘플 등록, 생성 상태, 삭제 상태 |

## 9. 구현 우선순위

1. 인증·회원 자동 생성: AUTH-001~006
2. 법률 문서·온보딩·프로필: LEGAL-001~002, ONBOARDING-001, MEMBER-001
3. 이력서·자기소개서: DOC-001~004
4. 지원공고 PDF·캡처 이미지(JPG·JPEG·PNG): JOB-001~005
5. 면접 설정: SESSION-001~003
6. 면접 진행: SESSION-004~005, QUESTION-001~002, ANSWER-001~002
7. 분석·결과: ANALYSIS-001~002, REPORT-001, AUDIO-001
8. 마이페이지: HISTORY-001, GROWTH-001
9. 동의·삭제: LEGAL-003~004, MEDIA-001~002, MEMBER-002~003
10. 후속 범위 음성 클론: LEGAL-001~004, VOICE-001~003
11. TELEMETRY-001 및 전체 보안·소유권·삭제·AI 연동 통합 검증

## 10. 내부 연동 구현 시 남은 운영 설정

프론트엔드 공개 계약에 필요한 항목은 12절에서 확정했습니다. 아래 항목은
공개 API의 Method·URI·DTO를 바꾸지 않는 백엔드·AI 내부 운영 설정입니다.

- OAuth provider별 client ID·secret과 운영 redirect URI
- 문서·지원공고 추출 worker의 실제 parser·OCR·AI provider
- AI·STT·CV·TTS·MuseTalk provider의 내부 URI, 인증정보, timeout
- 외부 분석 provider 재처리의 관리자 권한과 승인 절차
- 고아 Storage object 정리 worker의 실행 주기
- 음성 클론 provider callback 서명과 내부 model 삭제 재시도 횟수
- MuseTalk 캐릭터 원본 자산·TTS provider·렌더 worker의 timeout과 동시 처리량
- `schemaVersion` major upgrade 시 과거 리포트 migration 절차

## 11. 고정 Method·URI

아래 조합은 사용자 승인 없이 변경하지 않습니다.

| API ID | Method | URI |
| --- | --- | --- |
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
| DOC-005 | GET | `/api/v1/career-documents/{documentId}/analysis` |
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
| LEGAL-003 | POST | `/api/v1/legal-consents` |
| LEGAL-004 | DELETE | `/api/v1/legal-consents/{consentRecordId}` |
| MEMBER-002 | DELETE | `/api/v1/members/me` |
| MEMBER-003 | GET | `/api/v1/members/me/deletion` |
| SESSION-006 | POST | `/api/v1/interview-sessions/{sessionId}/clone` |
| QUESTION-002 | POST | `/api/v1/interview-sessions/{sessionId}/questions/{questionId}/character-media-access` |
| ANSWER-003 | POST | `/api/v1/interview-answers/{answerId}/media-access` |
| MEDIA-003 | GET | `/media/v1/playback/{playbackToken}` |
| ANALYSIS-002 | POST | `/api/v1/interview-sessions/{sessionId}/analysis-retry` |
| MEDIA-001 | DELETE | `/api/v1/interview-sessions/{sessionId}/media` |
| MEDIA-002 | GET | `/api/v1/interview-sessions/{sessionId}/media-deletion` |
| AUDIO-001 | GET | `/api/v1/reports/{reportId}/question-feedback/{feedbackId}/improved-answer-audio` |
| TELEMETRY-001 | POST | `/api/v1/client-events` |
| CONTEXT-001 | GET | `/api/v1/interview-sessions/{sessionId}/question-context` |

## 12. 프론트엔드 통합 확정 계약

### 12.1 확정 범위와 제품 결정

| 항목 | 확정 계약 |
| --- | --- |
| 기본 질문 수 | 5개 고정 |
| 꼬리 질문 | 각 기본 질문 답변당 0~1개, 최대 5개 |
| 전체 turn 수 | 5~10개 |
| 면접관 | `TECHNICAL`, `HR`, `EXECUTIVE` |
| 난이도 | `GENERAL`, `PRESSURE` |
| 면접 언어 | `ko-KR` 고정. 요청 필드 없음 |
| 이력서 | MVP 세션 생성 필수, `READY`만 허용 |
| 자기소개서 | 선택, 명시적 `null`로 연결 해제 |
| 지원공고 | 필수, `READY`이며 필수 구조화 필드 4개 필요 |
| 정상 종료 | 기본 질문 5개와 실제 생성된 꼬리 질문 모두 답변 완료 |
| 중도 종료 | `USER_INTERRUPTED`; 리포트 생성 안 함 |
| 답변 미디어 | 카메라 영상과 마이크 음성 stream이 모두 포함된 MP4 또는 WebM |
| 분석 | 실제 답변별 STT·CV·CONTENT 필수, 음성 분석 동의 시 VOICE 추가. 답변 10개 기준 총 30개 또는 40개 작업 |
| 부분 리포트 | 생성 안 함. 누락 점수를 0점 처리하지 않음 |
| 음성 프로필 | 선택 기능. 별도 동의 없으면 생성 금지 |
| 캐릭터 출력 | 질문별 TTS+MuseTalk MP4를 HTTPS 인증 streaming; 실패 시 정적 캐릭터+질문 텍스트 |

프론트의 `/onboarding`은 “새 면접 설정” 화면입니다. API의
`onboardingStatus`는 “가입 후 필수 법률 동의 완료 상태”입니다. 두 개념을
혼용하지 않습니다. 프론트는 가입 온보딩 화면을 `/account-onboarding`,
면접 설정 화면을 `/onboarding`으로 구분합니다.

`SESSION-004`는 해당 `sessionId`를 context로 가진 활성
`INTERVIEW_MEDIA_PROCESSING` 동의 기록이 있어야 성공합니다. 프론트는
`LEGAL-003` 성공 후에만 면접 시작을 요청합니다. 카메라나 마이크 track이
꺼지거나 종료되면 답변 녹화를 시작하지 않고 장비 복구 UI를 표시합니다.

### 12.2 환경·브라우저 인증 계약

| 구분 | 계약 |
| --- | --- |
| API origin | 프론트 환경변수 `VITE_API_BASE_URL` |
| OAuth provider | `google`, `kakao`, `naver`만 허용 |
| access token | 응답 JSON으로 전달, 브라우저 메모리에만 보관 |
| refresh token | `HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth` cookie |
| API 인증 | `Authorization: Bearer {accessToken}` |
| refresh 요청 | `credentials: "include"` 필수 |
| CORS | 운영 프론트 origin allowlist, `Allow-Credentials: true` |
| 시간 | ISO 8601 offset 포함. 서버 저장은 UTC |
| UUID | UUID v4 문자열 |

OAuth 흐름:

```text
GET /oauth2/authorization/{provider}
→ provider 인증
→ GET /login/oauth2/code/{provider}
→ 백엔드가 60초 유효·1회용 loginTicket 생성
→ 303 {FRONTEND_ORIGIN}/auth/callback?loginTicket={url-encoded-ticket}
→ POST /api/v1/auth/oauth/exchange
→ accessToken + refresh cookie + nextAction
```

`loginTicket`은 query string에서 교환 직후 `history.replaceState`로 제거합니다.
OAuth provider token은 프론트에 노출하지 않습니다. `AUTH-003`과
`AUTH-004`의 `accessTokenExpiresInSec`은 900입니다.

401 처리:

1. 프론트는 동시 refresh를 하나로 합칩니다.
2. `AUTH-004` 성공 후 원 요청을 한 번만 재시도합니다.
3. refresh 실패 시 access token을 폐기하고 `/login`으로 이동합니다.
4. 파일 업로드와 멱등성 없는 요청은 자동 재시도하지 않습니다.

### 12.3 공통 응답·오류·페이지네이션

JSON 성공 응답:

```json
{
  "success": true,
  "code": "SUCCESS",
  "message": "요청을 정상적으로 처리했습니다.",
  "data": {},
  "requestId": "01K1...",
  "timestamp": "2026-07-31T12:00:00Z"
}
```

JSON 오류 응답:

```json
{
  "success": false,
  "code": "VALIDATION_FAILED",
  "message": "입력값을 확인해 주세요.",
  "data": {
    "fieldErrors": [
      {
        "field": "difficulty",
        "reason": "INVALID_ENUM",
        "rejectedValue": "hard"
      }
    ],
    "retryable": false,
    "retryAfterSec": null
  },
  "requestId": "01K1...",
  "timestamp": "2026-07-31T12:00:00Z"
}
```

규칙:

- `204 No Content`, OAuth redirect, binary audio·video 응답에는 JSON envelope를 사용하지 않습니다.
- `requestId`는 모든 HTTP 응답의 `X-Request-Id` header와 동일합니다.
- 알 수 없는 JSON 필드는 `400 VALIDATION_FAILED`로 거부합니다.
- 목록 query의 기본값은 `page=0`, `size=20`; `size`는 1~100입니다.
- 정렬 기본값은 `createdAt,desc`이며 허용되지 않은 sort는 거부합니다.

페이지 응답 `data`:

```json
{
  "items": [],
  "page": 0,
  "size": 20,
  "totalElements": 0,
  "totalPages": 0,
  "hasNext": false
}
```

### 12.4 공통 DTO

#### 인증·회원

```ts
type MemberStatus = "ACTIVE" | "BLOCKED" | "WITHDRAWN";
type OnboardingStatus = "NOT_STARTED" | "IN_PROGRESS" | "COMPLETED";
type NextAction = "COMPLETE_ONBOARDING" | "GO_TO_SERVICE" | "RELOGIN";

type AuthData = {
  authenticated: boolean;
  accessToken: string | null;
  accessTokenExpiresInSec: number | null;
  member: MemberSummary | null;
  nextAction: NextAction;
};

type MemberSummary = {
  memberId: string;
  name: string;
  email: string;
  profileImageUrl: string | null;
  memberStatus: MemberStatus;
  onboardingStatus: OnboardingStatus;
  createdAt: string;
};
```

`AUTH-003`, `AUTH-004`, `AUTH-006`은 같은 `AuthData`를 사용합니다.
비로그인 `AUTH-006`은 HTTP 200과 `authenticated=false`,
`nextAction=RELOGIN`을 반환합니다.

#### 법률 문서·동의

```ts
type LegalDocumentType =
  | "TERMS_OF_SERVICE"
  | "PRIVACY_POLICY"
  | "INTERVIEW_MEDIA_PROCESSING"
  | "VOICE_CLONING";
type LegalActionType = "CONSENTED" | "ACKNOWLEDGED";
type ConsentStatus = "ACTIVE" | "REVOKED";

type LegalDocumentSummary = {
  documentId: string;
  type: LegalDocumentType;
  version: string;
  title: string;
  requiredForOnboarding: boolean;
  requiredAction: LegalActionType;
  effectiveAt: string;
};

type LegalDocumentDetail = LegalDocumentSummary & {
  contentFormat: "MARKDOWN";
  content: string;
};

type LegalConsentRecord = {
  consentRecordId: string;
  documentId: string;
  documentType: LegalDocumentType;
  documentVersion: string;
  actionType: LegalActionType;
  status: ConsentStatus;
  consentedAt: string;
  revokedAt: string | null;
};
```

#### 문서·지원공고

```ts
type ProcessingStatus = "PROCESSING" | "READY" | "FAILED";
type CareerDocumentType = "RESUME" | "COVER_LETTER";

type CareerDocument = {
  documentId: string;
  documentType: CareerDocumentType;
  originalFileName: string;
  sizeBytes: number;
  mimeType: string;
  status: ProcessingStatus;
  failureCode: string | null;
  createdAt: string;
  updatedAt: string;
};

type AiJobRole =
  | "AI_ENGINEER"
  | "ML_ENGINEER"
  | "DATA_SCIENTIST"
  | "DATA_ENGINEER"
  | "MLOPS_ENGINEER"
  | "LLM_ENGINEER"
  | "NLP_ENGINEER"
  | "COMPUTER_VISION_ENGINEER"
  | "AI_PRODUCT_MANAGER";

type JobPosting = {
  jobPostingId: string;
  inputType: "FILE";
  originalFileName: string | null;
  processingStatus: ProcessingStatus;
  companyName: string | null;
  targetJobRole: AiJobRole | null;
  mainResponsibilities: string[] | null;
  qualifications: string[] | null;
  preferredQualifications: string[] | null;
  technologiesTools: string[] | null;
  coreCompetencies: string[] | null;
  companyBusinessIntro: string | null;
  failureCode: string | null;
  createdAt: string;
  updatedAt: string;
};
```

`DOC-001` 허용 파일은 PDF·DOCX, 최대 10MB입니다. PDF 최대 50페이지,
암호화·손상 파일은 거부합니다. `DOC-001` 응답은 HTTP 202와
`CareerDocument`입니다.

`JOB-001`은 필수 FILE 규칙으로 10MB, PDF 50페이지, 이미지 40MP 이하입니다. 처리 실패 시 같은 리소스를 재시도하지 않고 새 `JOB-001`을 호출합니다.

#### 세션·질문·답변

```ts
type Persona = "TECHNICAL" | "HR" | "EXECUTIVE";
type Difficulty = "GENERAL" | "PRESSURE";
type SessionStatus =
  | "DRAFT"
  | "IN_PROGRESS"
  | "INTERVIEW_COMPLETED"
  | "ANALYZING"
  | "COMPLETED"
  | "INTERRUPTED";
type QuestionGenerationStatus = "NOT_STARTED" | "QUEUED" | "PROCESSING" | "SUCCEEDED" | "FAILED";
type FollowUpDecisionStatus = "NOT_APPLICABLE" | "QUEUED" | "PROCESSING" | "GENERATED" | "SKIPPED" | "FAILED_SKIPPED";
type CharacterMediaStatus = "QUEUED" | "PROCESSING" | "READY" | "FAILED_FALLBACK";
type QuestionKind = "BASE" | "FOLLOW_UP";
type QuestionCategory = "INTRO_MOTIVATION" | "EXPERIENCE" | "ROLE_JOB" | "SITUATION_COLLABORATION" | "GROWTH";
type AnswerStatus = "UPLOADED" | "PROCESSING" | "READY" | "FAILED";
type NextQuestionStatus = "WAITING" | "READY" | "INTERVIEW_COMPLETE";

type JobPostingSnapshot = {
  companyName: string;
  targetJobRole: AiJobRole;
  mainResponsibilities: string[];
  qualifications: string[];
  preferredQualifications: string[];
  technologiesTools: string[];
  coreCompetencies: string[];
  companyBusinessIntro: string | null;
};

type InterviewSession = {
  sessionId: string;
  status: SessionStatus;
  resumeDocumentId: string;
  coverLetterDocumentId: string | null;
  jobPostingId: string;
  persona: Persona;
  difficulty: Difficulty;
  baseQuestionCount: 5;
  generatedFollowUpCount: number;
  followUpFailureCount: number;
  completedFollowUpDecisionCount: number;
  knownTurnCount: number;
  finalTurnCount: number | null;
  answeredTurnCount: number;
  currentTurnOrder: number | null;
  questionGenerationStatus: QuestionGenerationStatus;
  characterMode: "MUSETALK_CLIP";
  jobPostingSnapshot: JobPostingSnapshot;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  interruptedAt: string | null;
};

type InterviewQuestion = {
  questionId: string;
  turnOrder: number;
  baseQuestionOrder: number;
  baseQuestionCount: 5;
  questionKind: QuestionKind;
  parentQuestionId: string | null;
  category: QuestionCategory;
  text: string;
  answerStatus: "NOT_SUBMITTED" | AnswerStatus;
  characterMediaStatus: CharacterMediaStatus;
  characterMediaDurationMs: number | null;
  characterMediaAccessRequired: true;
  characterFallback: "NONE" | "STATIC_CHARACTER_TEXT";
};

type InterviewAnswer = {
  answerId: string;
  sessionId: string;
  questionId: string;
  status: AnswerStatus;
  recordedDurationMs: number;
  mediaDurationMs: number;
  endedBy: "USER_BUTTON" | "SPACE_KEY" | "SILENCE_CONFIRMED";
  followUpDecisionStatus: FollowUpDecisionStatus;
  nextQuestionStatus: NextQuestionStatus;
  nextQuestionId: string | null;
  processingSteps: Array<{
    type: "STT" | "CV" | "VOICE" | "CONTENT";
    status: "QUEUED" | "PROCESSING" | "SUCCEEDED" | "FAILED" | "DEPENDENCY_FAILED";
    failureCode: string | null;
  }>;
  createdAt: string;
  updatedAt: string;
};

type PlaybackAccess = {
  playbackUrl: string;
  expiresAt: string;
  mediaDurationMs: number;
  clipStartMs: number;
  clipEndMs: number;
};
```

`knownTurnCount`는 현재까지 확정된 기본 질문과 꼬리 질문 수입니다.
`finalTurnCount`는 기본 질문 5개의 꼬리 질문 결정이 모두 끝나기 전에는
`null`, 이후 5~10입니다. 프론트는 진행 중인 `knownTurnCount`를 최종 질문
수처럼 표시하지 않습니다.

`QUESTION-001` 응답:

- 기본 질문 생성 중: HTTP 202,
  `data={questionGenerationStatus:"PROCESSING",followUpDecisionStatus:"NOT_APPLICABLE",retryAfterSec:2}`
- 꼬리 질문 결정 중: HTTP 202,
  `data={questionGenerationStatus:"SUCCEEDED",followUpDecisionStatus:"PROCESSING",retryAfterSec:2}`
- 질문 또는 MuseTalk 영상 준비 중: HTTP 202,
  `data={questionGenerationStatus:"SUCCEEDED",characterMediaStatus:"PROCESSING",retryAfterSec:2}`
- 현재 질문과 영상 준비 완료: HTTP 200, `InterviewQuestion`
- MuseTalk 생성 실패: HTTP 200 `InterviewQuestion` with
  `characterMediaStatus="FAILED_FALLBACK"`, `characterMediaDurationMs=null`,
  `characterFallback="STATIC_CHARACTER_TEXT"`
- 모든 답변 완료: HTTP 200, `data={nextQuestionStatus:"INTERVIEW_COMPLETE", question:null}`
- 생성 최종 실패: HTTP 503 `QUESTION_GENERATION_FAILED`

`ANSWER-001` 응답은 HTTP 202와 `InterviewAnswer`입니다. 프론트는 응답의
`answerId`로 `ANSWER-002`를 조회합니다. 다음 질문은 답변 업로드 트랜잭션이
확정된 뒤 빠른 STT와 꼬리 질문 결정 작업을 거쳐 준비합니다. 전체 CV·VOICE·
CONTENT 분석 완료를 기다리지 않습니다. 기본 질문 답변이면
`followUpDecisionStatus=QUEUED`, 꼬리 질문 답변이면
`followUpDecisionStatus=NOT_APPLICABLE`입니다.

`nextQuestionStatus=READY`는 다음 질문의 `characterMediaStatus`가 `READY` 또는
`FAILED_FALLBACK`으로 확정된 뒤에만 반환합니다. `QUEUED|PROCESSING`이면
`WAITING`을 유지합니다.

꼬리 질문 결정은 다음 규칙을 사용합니다.

1. 기본 질문 답변의 빠른 STT 성공 후 LLM에 질문·전사·세션 snapshot 전달
2. 보완 필요하면 꼬리 질문 1개 저장 후 `GENERATED`
3. 보완 불필요하면 `SKIPPED`
4. timeout·provider 실패면 `FAILED_SKIPPED` 후 다음 기본 질문 진행
5. 생성 결과가 안전 정책을 통과하지 못하면 저장하지 않고 `FAILED_SKIPPED`
6. 결정 timeout은 8초, 전체 다음 질문 준비 목표는 P95 10초

`ANSWER-001.recordedDurationMs`는 1,000~300,000 정수입니다. `SILENCE_CONFIRMED`는 3,000 이상이어야 합니다. multipart `file`의
실제 media duration과 2초 넘게 차이나면 `INVALID_ANSWER_MEDIA`로
거부합니다.

프론트는 마지막 기본 질문 답변 후에도 `ANSWER-002` 또는 `QUESTION-001`의
`nextQuestionStatus=INTERVIEW_COMPLETE`를 확인하기 전 `SESSION-005 NORMAL`을
호출하지 않습니다. 꼬리 질문 결정 중 호출하면
`409 FOLLOW_UP_DECISION_IN_PROGRESS`, 미답변 turn이 있으면
`409 INCOMPLETE_INTERVIEW`를 반환합니다.

### 12.5 API별 요청·응답 계약

기존 표에 없는 필드는 이 절을 따릅니다.

| API | 요청 | 성공 |
| --- | --- | --- |
| AUTH-003 | JSON `{loginTicket:string}` | 200 `AuthData`, refresh cookie |
| AUTH-004 | body 없음, refresh cookie | 200 `AuthData`, refresh cookie 회전 |
| AUTH-005 | body 없음 | 204, refresh cookie 만료 |
| LEGAL-001 | query `type?` | 200 `LegalDocumentSummary[]` |
| LEGAL-002 | path `documentId` | 200 `LegalDocumentDetail` |
| ONBOARDING-001 | JSON `{legalActions:{documentId,actionType}[],voiceAnalysisConsent:boolean}` | 200 `{onboardingStatus,voiceAnalysisConsent,voiceAnalysisConsentedAt,nextAction}` |
| MEMBER-001 | body 없음 | 200 `MemberSummary` |
| DOC-001 | multipart `file`, `documentType` | 202 `CareerDocument` |
| DOC-002 | query `documentType?`, `status?`, page | 200 page of `CareerDocument` |
| DOC-003 | path `documentId` | 200 `CareerDocument` |
| DOC-004 | path `documentId` | 204 |
| DOC-005 | path `documentId` | 200 `ResumeInterviewProfileSummary` |
| JOB-001 | multipart 필수 FILE (`targetJobRole`, `file`) | 202 `JobPosting` |
| JOB-002 | query `processingStatus?`, page | 200 page of `JobPosting` |
| JOB-003 | path `jobPostingId` | 200 `JobPosting` |
| JOB-004 | JSON 구조화 필드 subset | 200 `JobPosting` |
| JOB-005 | path `jobPostingId` | 204 |
| SESSION-001 | JSON `{resumeDocumentId,coverLetterDocumentId?,jobPostingId,persona,difficulty}` | 201 `InterviewSession` |
| SESSION-002 | path `sessionId` | 200 `InterviewSession` |
| SESSION-003 | JSON 변경 필드 subset | 200 `InterviewSession` |
| SESSION-004 | `Idempotency-Key`, body 없음 | 202 `InterviewSession` |
| SESSION-005 | `Idempotency-Key`, JSON `{completionType}` | 200 `InterviewSession` |
| QUESTION-001 | path `sessionId` | 200 `InterviewQuestion` 또는 완료 상태, 준비 중 202 |
| QUESTION-002 | path `sessionId`,`questionId`, `Range?` | 200/206 `video/mp4`, 준비 중 202, 폴백 409 |
| ANSWER-001 | `Idempotency-Key`, multipart | 202 `InterviewAnswer` |
| ANSWER-002 | path `answerId` | 200 `InterviewAnswer` |
| ANALYSIS-001 | path `sessionId` | 200 `AnalysisStatus` |
| REPORT-001 | path `sessionId` | 200/202 `ReportData` 또는 생성 상태 |
| HISTORY-001 | query `status?`, page | 200 page of `InterviewHistoryItem` |
| GROWTH-001 | query `limit=5`, `from?`, `to?` | 200 `GrowthData` |
| VOICE-001 | multipart `consentRecordId`, `file` | 202 `VoiceProfile` |
| VOICE-002 | body 없음 | 200 `VoiceProfile`, 없으면 404 |
| VOICE-003 | body 없음 | 202 `VoiceProfile` with `DELETING` |
| CONTEXT-001 | path `sessionId` | 200 `QuestionContextTransparency` |

### 12.6 신규 API

#### LEGAL-003 기능별 동의 기록

`POST /api/v1/legal-consents`

```json
{
  "documentId": "legal-document-uuid",
  "actionType": "CONSENTED",
  "context": {
    "sessionId": "session-uuid"
  }
}
```

- `VOICE_CLONING`: `context.sessionId` 불필요
- `INTERVIEW_MEDIA_PROCESSING`: 대상 면접의 `sessionId` 필수
- 최신 활성 문서에만 동의 가능
- 성공: HTTP 201 `LegalConsentRecord`
- 같은 문서·context에 활성 동의가 있으면 기존 record를 HTTP 200으로 반환

#### LEGAL-004 동의 철회

`DELETE /api/v1/legal-consents/{consentRecordId}`

- 성공: HTTP 202 `{consentRecord, dependentDeletionStatus}`
- 음성 동의 철회 시 음성 프로필 즉시 `usable=false`, 삭제 작업 등록
- 면접 미디어 동의는 해당 세션 녹화 시작 후 철회할 수 없습니다. 사용자는
  `MEDIA-001` 또는 `SESSION-005 USER_INTERRUPTED`를 사용합니다.

#### MEMBER-002~003 계정 삭제

`DELETE /api/v1/members/me`

```json
{
  "confirmation": "DELETE_MY_ACCOUNT"
}
```

성공은 HTTP 202이며 access token과 refresh cookie를 즉시 폐기합니다.

```ts
type DeletionStatus = "QUEUED" | "PROCESSING" | "COMPLETED" | "FAILED";
type MemberDeletion = {
  deletionRequestId: string;
  status: DeletionStatus;
  requestedAt: string;
  completedAt: string | null;
  failedTargets: string[];
};
```

`GET /api/v1/members/me/deletion`은 삭제 요청 때 발급한 24시간 유효
`Deletion-Status-Token` header로 조회합니다. 회원 인증정보가 이미 폐기된
뒤에도 삭제 결과를 확인하기 위한 전용 token입니다.

#### SESSION-006 재연습 설정 복제

`POST /api/v1/interview-sessions/{sessionId}/clone`

```json
{
  "growthTaskId": "growth-task-uuid"
}
```

- 원 세션 설정과 유효한 문서·지원공고 ID를 복사
- 삭제·미준비 리소스가 있으면 `409 RESOURCE_NOT_READY`
- 성장 과제는 선택이며 원 세션 소유인지 확인
- 성공: HTTP 201 `InterviewSession` with `status=DRAFT`

#### QUESTION-002 MuseTalk 캐릭터 미디어

`POST /api/v1/interview-sessions/{sessionId}/questions/{questionId}/character-media-access`

- 현재 로그인 회원 소유 세션의 현재 질문만 허용
- `characterMediaStatus=READY`: HTTP 200 `PlaybackAccess` (`clipStartMs=0`, `clipEndMs=mediaDurationMs`)
- 준비 중: HTTP 202 JSON

```json
{
  "status": "PROCESSING",
  "retryAfterSec": 2
}
```

- 생성 실패: HTTP 409 `CHARACTER_MEDIA_UNAVAILABLE`; 프론트는 정적 캐릭터와 질문 텍스트 사용
- `playbackUrl`은 `GET /media/v1/playback/{playbackToken}`이다. 브라우저 `<video>`는 Authorization 헤더를 붙일 수 없으므로, 프론트가 Bearer 인증된 이 API로 권한을 교환한 뒤 `video.src=playbackUrl`로 설정한다.
- `playbackToken`은 소유 회원·미디어·재생 범위에 묶인 opaque token이며 60초 후 만료한다. token은 Range 재요청을 위해 만료 전 재사용 가능하나 Storage URL·Storage key는 아니다.
- MEDIA-003은 `Range` 요청을 지원하며 HTTP 206, `Accept-Ranges: bytes`, `Cache-Control: private, no-store`, `Content-Disposition: inline`을 반환한다.
- 응답 MP4에는 TTS 음성과 MuseTalk 립싱크 영상이 함께 포함됨
- MP4 codec은 H.264(`avc1`) video + AAC-LC audio, 최대 1280×720, 24fps, 질문당 최대 60초
- 같은 질문 다시 듣기는 저장된 MP4를 다시 재생하며 새 생성 요청을 만들지 않음
- Storage key, 내부 파일 URL, TTS·MuseTalk provider 식별자는 응답·로그에 노출하지 않음

#### ANSWER-003 답변 근거 영상 재생

`POST /api/v1/interview-answers/{answerId}/media-access`

```json
{ "startMs": 12000, "endMs": 18000 }
```

- 본인 답변만 허용한다. `0 <= startMs < endMs <= mediaDurationMs`, 최대 구간 60,000ms를 검증한다.
- 성공: HTTP 200 `PlaybackAccess`. `clipStartMs`, `clipEndMs`는 요청값을 그대로 반환한다.
- 프론트는 `video.src=playbackUrl`, `video.currentTime=clipStartMs/1000`으로 시작하고 `clipEndMs` 도달 시 pause한다. 리포트의 `QuestionFeedback.answerId`로 답변을 지정한다.
- 만료 token: `401 PLAYBACK_ACCESS_EXPIRED`; 범위 오류: `400 PLAYBACK_RANGE_INVALID`. 재생 권한을 다시 발급받는다.

#### ANALYSIS-002 실패 분석 재시도

`POST /api/v1/interview-sessions/{sessionId}/analysis-retry`

```json
{
  "failedStepsOnly": true
}
```

- `analysisStatus=FAILED`, `retryable=true`일 때만 허용
- Header `Idempotency-Key` 필수
- 성공: HTTP 202 `AnalysisStatus`
- 사용자 재시도 최대 2회, 이후 `409 RETRY_LIMIT_EXCEEDED`

#### MEDIA-001~002 면접 원본 미디어 삭제

`DELETE /api/v1/interview-sessions/{sessionId}/media`

```json
{
  "scope": "ORIGINAL_MEDIA"
}
```

- 원본 영상·음성만 삭제하고 리포트·점수는 보존
- 분석 중이면 `409 RESOURCE_IN_USE`
- 성공: HTTP 202 `MediaDeletion`

```ts
type MediaDeletion = {
  deletionRequestId: string;
  sessionId: string;
  status: DeletionStatus;
  objectCount: number;
  requestedAt: string;
  completedAt: string | null;
};
```

`GET /api/v1/interview-sessions/{sessionId}/media-deletion`으로 조회합니다.

#### AUDIO-001 개선 답변 음성

`GET /api/v1/reports/{reportId}/question-feedback/{feedbackId}/improved-answer-audio?voiceType=STANDARD|PERSONAL`

- `STANDARD`: 별도 음성 동의 불필요
- `PERSONAL`: `VOICE-002 usable=true` 필요
- 성공: `200 audio/mpeg`, `Cache-Control: private, max-age=300`
- `Accept-Ranges: bytes` 지원
- 음성 준비 중: HTTP 202 JSON `{status:"PROCESSING",retryAfterSec:3}`
- 개인 음성 미사용: `409 VOICE_PROFILE_NOT_READY`

#### TELEMETRY-001 프론트 이벤트

`POST /api/v1/client-events`

```json
{
  "eventId": "uuid",
  "eventName": "answer_upload_failed",
  "occurredAt": "2026-07-31T12:00:00Z",
  "sessionId": "session-uuid",
  "properties": {
    "errorCode": "NETWORK_ERROR",
    "retryCount": 1
  }
}
```

- 최대 20개 batch array 허용
- 원문 답변, 파일명, email, token, Storage key 전송 금지
- 성공: HTTP 202, 중복 `eventId` 무시

### 12.7 MuseTalk 캐릭터 미디어 계약

```text
질문 저장
→ TTS 음성 생성
→ MuseTalk이 고정 캐릭터 자산과 TTS 음성으로 MP4 생성
→ Private Storage 저장
→ characterMediaStatus=READY
→ QUESTION-001이 미디어 상태·길이 제공
→ QUESTION-002가 `PlaybackAccess` 발급
→ 브라우저가 MEDIA-003으로 MP4 Range streaming
```

- 캐릭터는 면접관 유형별 사전 승인된 고정 자산을 사용한다.
- 질문별 영상은 짧은 MP4 클립이며 지속 연결·실시간 frame·WebSocket·WebRTC를 사용하지 않는다.
- 대기·듣기·로딩 반응은 프론트 정적 이미지·CSS animation으로 구현한다. 백엔드는 말하는 질문 MP4만 제공한다.
- 프론트는 영상 재생이 끝난 뒤 답변 녹음을 시작한다. 사용자가 영상을 중단해도 서버 호출은 필요 없다.
- MuseTalk 실패·timeout이면 `FAILED_FALLBACK`으로 저장하고 정적 캐릭터+질문 텍스트로 면접을 계속한다.
- TTS만 성공해도 별도 audio URL을 공개하지 않는다. 초기 MVP 폴백은 정적 캐릭터+텍스트로 고정한다.
- 같은 `questionId`의 렌더 작업은 멱등적이며 캐시된 결과를 재사용한다.
- 목표 처리시간은 P95 10초, hard timeout은 20초다. 20초 초과 또는 재시도 1회 실패 시 `FAILED_FALLBACK`으로 확정한다.
- 기본 질문 5개는 질문 계획 완료 후 순서대로 선생성할 수 있다. 꼬리질문은 답변 기반 생성이므로 결정 완료 뒤에만 렌더한다.
- 캐릭터 자산 권리, TTS 음성 권리, 생성 영상 보존기간을 배포 전에 승인한다.

### 12.8 분석·리포트 DTO

```ts
type AnalysisStageCount = {
  total: number;
  queued: number;
  processing: number;
  succeeded: number;
  failed: number;
};

type AnalysisStatus = {
  sessionId: string;
  sessionStatus: SessionStatus;
  analysisStatus: "WAITING" | "PROCESSING" | "SUCCEEDED" | "FAILED";
  totalAnswerCount: number;
  completedAnswerCount: number;
  failedAnswerCount: number;
  totalRequiredTaskCount: number;
  succeededRequiredTaskCount: number;
  progressPercent: number;
  currentUiStage: "PREPARING" | "VOICE" | "VISION" | "CONTENT" | "REPORT";
  stages: {
    stt: AnalysisStageCount;
    cv: AnalysisStageCount;
    voice: AnalysisStageCount;
    content: AnalysisStageCount;
  };
  reportStatus: "WAITING_FOR_ANALYSIS" | "QUEUED" | "PROCESSING" | "SUCCEEDED" | "FAILED";
  failureCode: "ANSWER_ANALYSIS_FAILED" | "BLOCKED_BY_ANALYSIS_FAILURE" | "REPORT_GENERATION_FAILED" | null;
  retryable: boolean;
  retryCount: number;
  retryAfterSec: number | null;
  updatedAt: string;
};

type ReportEvidence = {
  label: string;
  value: string;
  questionId: string | null;
  startMs: number | null;
  endMs: number | null;
};

type ReportImprovement = {
  improvementId: string;
  axis: "GAZE" | "POSTURE" | "SPEECH" | "CONTENT";
  title: string;
  reason: string;
  practice: string;
  priority: number;
};

type QuestionFeedback = {
  feedbackId: string;
  questionId: string;
  answerId: string;
  order: number;
  question: string;
  answerSummary: string;
  score: number;
  evidence: ReportEvidence[];
  improvedAnswerText: string;
  improvementReason: string;
  audioAvailability: {
    standard: "READY" | "PROCESSING" | "FAILED";
    personal: "UNAVAILABLE" | "PROCESSING" | "READY" | "FAILED";
  };
};

type ReportData = {
  sessionId: string;
  sessionStatus: "COMPLETED";
  reportStatus: "SUCCEEDED";
  report: {
    reportId: string;
    schemaVersion: "1.0";
    rubricVersion: string;
    overallScore: number;
    scores: {
      gaze: number;
      posture: number;
      speech: number | null;
      content: number;
    };
    strengths: Array<{
      axis: "GAZE" | "POSTURE" | "SPEECH" | "CONTENT";
      title: string;
      description: string;
      evidence: ReportEvidence[];
    }>;
    improvements: ReportImprovement[];
    questionFeedback: QuestionFeedback[];
    disclaimer: string;
    generatedAt: string;
  };
};
```

전체 STT 전문은 반환하지 않습니다. `answerSummary`는 공개용 요약이며 원문을
복원할 수 있는 긴 인용을 포함하지 않습니다.

### 12.9 이력·성장 DTO

```ts
type InterviewHistoryItem = {
  sessionId: string;
  reportId: string | null;
  sessionStatus: SessionStatus;
  analysisStatus: "WAITING" | "PROCESSING" | "SUCCEEDED" | "FAILED" | null;
  companyName: string;
  targetJobRole: AiJobRole;
  persona: Persona;
  difficulty: Difficulty;
  overallScore: number | null;
  completedAt: string | null;
  createdAt: string;
};

type GrowthPoint = {
  sessionId: string;
  reportId: string;
  completedAt: string;
  overallScore: number;
  scores: {
    gaze: number;
    posture: number;
    speech: number | null;
    content: number;
  };
};

type GrowthData = {
  points: GrowthPoint[];
  dataSufficiency: "INSUFFICIENT" | "SUFFICIENT";
  mostImprovedAxis: "GAZE" | "POSTURE" | "SPEECH" | "CONTENT" | null;
  priorityAxis: "GAZE" | "POSTURE" | "SPEECH" | "CONTENT" | null;
  latestImprovement: ReportImprovement | null;
};
```

대시보드 추천 연습은 `latestImprovement`를 사용합니다. 프론트가 임의로
점수 차이에서 코칭 문구를 만들지 않습니다.

### 12.10 음성 프로필 DTO·파일 계약

```ts
type VoiceProfile = {
  voiceProfileId: string;
  voiceStatus: "QUEUED" | "PROCESSING" | "READY" | "FAILED" | "DELETING";
  usable: boolean;
  failureCode: "INVALID_SAMPLE" | "INSUFFICIENT_AUDIO" | "MODEL_CREATION_FAILED" | "MODEL_DELETION_FAILED" | null;
  createdAt: string;
  completedAt: string | null;
  deletionCompletedAt: string | null;
};
```

- 허용: `audio/webm`, `audio/mp4`, `audio/wav`
- 실제 container·audio stream 검증 필수
- 15~60초, 최대 20MB
- mono/stereo 허용, 서버에서 16kHz mono PCM으로 정규화
- 무음 비율 50% 초과, clipping 비율 5% 초과, 음성 미검출은
  `400 INVALID_VOICE_SAMPLE`
- 재녹음은 기존 프로필을 먼저 `VOICE-003`으로 삭제 완료한 뒤 생성
- 외부 model ID, Storage key, signed URL은 JSON 응답에 포함하지 않음

### 12.11 HTTP 상태·재시도·멱등성

| 상황 | 상태·계약 |
| --- | --- |
| 동기 조회 성공 | 200 |
| 리소스 생성 완료 | 201 |
| 비동기 작업 등록 | 202 |
| body 없는 성공 | 204 |
| 유효성 오류 | 400 |
| 인증 없음·만료 | 401 |
| 온보딩·동의·권한 부족 | 403 |
| 본인 리소스 아님 | 404 |
| 상태 충돌·중복 | 409 |
| 파일 용량 | 413 |
| 파일 형식 | 415 |
| 요청 속도 제한 | 429 + `Retry-After` |
| 내부 오류 | 500 |
| 외부 AI 일시 오류 | 502 |
| 질문·리포트 최종 생성 실패 | 503 |

GET polling:

- 질문 생성: 2초, 최대 60초
- 답변 상태: 2초, 다음 질문 준비까지 최대 30초
- 분석 상태: 처음 30초는 3초, 이후 10초
- 음성 프로필: 3초, 최대 5분
- 삭제 상태: 5초
- 응답의 `retryAfterSec`가 있으면 해당 값을 우선
- 429·502·503만 exponential backoff와 jitter로 최대 3회 자동 재시도

멱등성:

- `SESSION-004`, `SESSION-005`, `ANSWER-001`, `ANALYSIS-002` 필수
- key 보존 24시간
- 최초 status·body·관련 response header까지 재사용
- multipart hash는 정규 필드와 실제 file SHA-256으로 계산

### 12.12 프론트 라우트·API 매핑

| 프론트 route | 식별자 | 최초 호출 |
| --- | --- | --- |
| `/auth/callback` | `loginTicket` query | AUTH-003 |
| `/account-onboarding` | 없음 | LEGAL-001, LEGAL-002 |
| `/onboarding` | 신규 설정 | DOC-002, JOB-002 |
| `/equipment/:sessionId` | `sessionId` | SESSION-002 |
| `/consent/:sessionId` | `sessionId` | LEGAL-001, LEGAL-003 |
| `/voice-profile/:sessionId` | `sessionId` | VOICE-002 |
| `/sessions/:sessionId/live` | `sessionId` | SESSION-002, SESSION-004, QUESTION-001 |
| `/sessions/:sessionId/analysis` | `sessionId` | ANALYSIS-001 |
| `/sessions/:sessionId/report` | `sessionId` | REPORT-001 |
| `/dashboard` | 없음 | MEMBER-001, HISTORY-001, GROWTH-001 |
| `/records/:sessionId` | `sessionId` | REPORT-001 |

route 진입 시 브라우저 메모리 상태를 신뢰하지 않고 URL의 `sessionId`로
서버 상태를 재조회합니다. 권한 없는 ID는 리소스 존재 여부를 숨기기 위해
404로 처리합니다.

`/sessions/:sessionId/live`는 SESSION-004 후 QUESTION-001을 polling합니다.
`characterMediaStatus=READY`이면 QUESTION-002로 `PlaybackAccess`를 발급받고 MEDIA-003 MP4를 재생하며,
`FAILED_FALLBACK`이면 정적 캐릭터와 질문 텍스트로 진행합니다.

### 12.13 프론트 상태 매핑

| 화면 상태 | 서버 기준 |
| --- | --- |
| 질문 생성 중 | SESSION-004 202 또는 QUESTION-001 202 |
| 캐릭터 영상 생성 중 | `characterMediaStatus=QUEUED|PROCESSING` |
| 캐릭터 영상 재생 가능 | `characterMediaStatus=READY`, QUESTION-002가 발급한 유효한 `PlaybackAccess` |
| 캐릭터 폴백 | `characterMediaStatus=FAILED_FALLBACK`, 정적 캐릭터+텍스트 |
| 답변 저장 중 | ANSWER-001 요청 중 |
| 다음 질문 준비 | `nextQuestionStatus=WAITING` |
| 다음 질문 가능 | `nextQuestionStatus=READY` |
| 꼬리 질문 결정 중 | `followUpDecisionStatus=QUEUED|PROCESSING` |
| 꼬리 질문 표시 | `InterviewQuestion.questionKind=FOLLOW_UP` |
| 질문 진행 표시 | 기본 질문은 `baseQuestionOrder / 5`, 꼬리 질문은 `꼬리 질문` badge |
| 정상 종료 가능 | 기본 질문 5개, 생성된 꼬리 질문 전부 답변, 마지막 결정 완료 |
| 분석 중 | `sessionStatus=ANALYZING`, `analysisStatus=PROCESSING` |
| 분석 지연 | `retryAfterSec` 경과 후에도 PROCESSING |
| 분석 실패 | `analysisStatus=FAILED` |
| 리포트 가능 | `sessionStatus=COMPLETED`, `reportStatus=SUCCEEDED` |
| 개인 음성 재생 가능 | `voiceStatus=READY`, `usable=true` |

### 12.14 보안·보존·삭제 확정

| 데이터 | 기본 보존 |
| --- | --- |
| 답변 원본 영상·음성 | 세션 완료·중단 후 30일 |
| 질문 MuseTalk MP4 | 세션 완료·중단 후 30일; 캐릭터 원본 자산은 별도 운영 자산 정책 |
| STT 전문 | 30일 |
| 파생 분석 특징 | 1년 |
| 리포트·공개 피드백 | 회원 탈퇴 전까지 |
| 이력서·자기소개서·지원공고 원본 | 사용자 삭제 또는 회원 탈퇴 전까지 |
| 음성 샘플·미리듣기·복제 모델 | 동의 철회·프로필 삭제·회원 탈퇴 시 삭제 |
| API 감사 로그 | 90일, 원문·token·Storage key 제외 |
| 멱등성 기록 | 24시간 |

삭제는 논리 삭제 후 Worker가 외부 AI·Private Storage·DB 파생 참조를
삭제합니다. 외부 삭제 실패는 `FAILED`로 추적하며 자동 재시도합니다.
백업 데이터는 최대 30일 내 순환 삭제하며 서비스 조회 대상에서 즉시
제외합니다.

모든 사용자 리소스 조회는 인증 subject와 resource owner를 함께 조건으로
사용합니다. Storage provider signed URL은 공개 API 응답에 사용하지 않습니다. MEDIA-003의 opaque playback token은 60초 재생 전용 권한이며, binary streaming endpoint가 범위·만료·소유권을 검증합니다.

### 12.15 완료 조건

프론트·백엔드 통합 완료는 다음을 모두 충족해야 합니다.

1. 본 문서의 Method·URI·enum·DTO를 OpenAPI 3.1로 생성하고 CI에서 검증
2. OpenAPI로 프론트 TypeScript 타입 생성, 수기 중복 타입 금지
3. contract test에서 성공·오류·202 polling·멱등성 사례 검증
4. QUESTION-002·ANSWER-003이 Bearer 인증으로 60초 `PlaybackAccess`를 발급하고 MEDIA-003 Range 재생·만료 재발급을 검증
5. AI worker job 등록·HMAC callback·중복 revision 무시·내부 오류 상태 저장을 contract test로 검증
6. VAD 3초 guard, 2초 무음, 1초 카운트다운 취소와 `endedBy` 저장을 E2E로 검증
7. OAuth 세 provider, refresh 동시 요청, 로그아웃 검증
5. 기본 5문항과 기본 질문당 꼬리 질문 0~1개 녹화·업로드·정상 종료·중도 종료 E2E 검증
6. MuseTalk 영상 준비·Range 재생·캐시·생성 실패·정적 캐릭터 폴백 검증
7. 분석 성공·실패·재시도·리포트 생성 검증
8. 동의 생성·철회, 미디어 삭제, 음성 삭제, 회원 탈퇴 검증
9. 다른 회원 UUID 접근이 모두 404인지 검증
10. 로그·응답에 token, 원문, Storage key, 외부 model ID가 없는지 검증

### 12.16 Agentic RAG·이력서 분석 계약

이 절은 프론트·백엔드가 공유하는 공개 DTO와 내부 job 경계를 고정한다.

```ts
type ResumeInterviewProfileSummary = {
  documentId: string;
  profileVersion: "1.0";
  status: "PROCESSING" | "READY" | "FAILED";
  skills: Array<{ name: string; evidenceRefCount: number }>;
  experienceCount: number;
  projectCount: number;
  missingInformation: string[];
  qualityFlags: Array<"LOW_TEXT_QUALITY" | "OCR_UNCERTAIN" | "AMBIGUOUS_DATE" | "NO_PROJECT_EVIDENCE">;
  analyzerVersion: string | null;
  analyzedAt: string | null;
};

type QuestionEvidenceSummary = {
  evidenceId: string;
  sourceType: "RESUME" | "JOB_POSTING" | "OFFICIAL_COMPANY_SOURCE" | "ROLE_TEMPLATE";
  title: string;
  sourceDomain: string | null;
  publishedAt: string | null;
  freshnessStatus: "FRESH" | "STALE" | null;
  summary: string;
};

type QuestionContextTransparency = {
  sessionId: string;
  generationMode: "RAG_GROUNDED" | "JOB_POSTING_ONLY" | "ROLE_TEMPLATE";
  promptVersion: string;
  resumeProfileStatus: "PROCESSING" | "READY" | "FAILED";
  retrievalStatus: "NOT_USED" | "READY" | "NO_RELIABLE_EVIDENCE" | "FAILED_FALLBACK";
  questions: Array<{
    questionId: string;
    evidence: QuestionEvidenceSummary[];
  }>;
  generatedAt: string;
};
```

`DOC-005`는 현재 회원 소유 문서의 요약 결과만 반환한다. 원문 문장, email,
전화번호, 주소, 사진, 보호 특성, embedding, prompt는 반환하지 않는다.
`CONTEXT-001`은 세션 소유자에게만 제공하며 source summary는 최대 240자다.

내부 Agent job:

| jobType | 입력 | 출력 | 실패 처리 |
| --- | --- | --- | --- |
| `RESUME_ANALYSIS` | 검증된 문서 text·문서 유형 | `ResumeInterviewProfile` | quality flag 저장, 직무 template 폴백 |
| `COMPANY_RETRIEVAL` | 기업·직무·지원공고 snapshot | 승인 source evidence | `NO_RELIABLE_EVIDENCE`, 공고 전용 폴백 |
| `QUESTION_PLANNING` | profile·공고·retrieval·persona·difficulty | 기본 질문 5개와 evidence refs | JSON repair 1회 후 template 폴백 |
| `FOLLOW_UP_DECISION` | 기본 질문·빠른 STT·근거 | 꼬리 질문 0~1개 또는 skip | 8초 timeout 후 `FAILED_SKIPPED` |

Agent는 승인된 retrieval index read, session context read, 검증된 question
write command만 호출한다. tool 최대 6회, retrieval 최대 2회, LLM 최대 2회,
총 20초 budget을 넘기면 `AGENT_BUDGET_EXCEEDED`를 기록하고 질문 template으로
종료한다. Agent는 외부 URL fetch, shell, DB 직접 query, 계정 조회, 결제,
외부 메시지 전송 권한이 없다.

Prompt는 `promptVersion`, `modelProvider`, `modelVersion`, `temperature`,
`contextSnapshotVersion`, `retrievalId`, `indexVersion`을 결과와 함께 저장한다.
이력서·지원공고·RAG chunk·STT 전문은 untrusted data로 delimiter 처리한다.
“이전 지시를 무시”, prompt 공개, 점수 변경, tool 호출 요구는 data로만 처리하며
안전 규칙을 변경할 수 없다.

질문과 꼬리 질문은 evidenceRef가 있거나 `ROLE_TEMPLATE` fallback reason이
있어야 저장할 수 있다. 근거 없는 기업·이력서 사실, 민감 주제, 차별·모욕 표현,
실시간 평가·합격 예측은 validator가 거부한다.
