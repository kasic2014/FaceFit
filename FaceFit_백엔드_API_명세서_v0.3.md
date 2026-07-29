# FaceFit 백엔드 API 명세서 v0.3

| 항목 | 내용 |
| --- | --- |
| 문서 목적 | 백엔드 구현 및 프론트엔드·AI 담당자와의 연동 기준 공유 |
| 기준 자료 | FACE-FIT 기획서·화면설계서, API 명세서 v0.1, 테이블 명세서 v0.3, 사용자 확정 정책 |
| 작성 범위 | 백엔드가 제공하는 API와 백엔드가 담당하는 AI 연동 경계 |
| 제외 범위 | AI 모델 내부 알고리즘, 프롬프트, 점수 계산식, 모델 학습 방식 |
| 버전 | v0.3 |
| 작성일 | 2026-07-28 |

> v0.3에서는 온보딩 구조와 지원공고 FILE·TEXT 입력 구조를 유지하면서 음성 클론 `VOICE-001~003`을 이번 MVP 구현 범위에 포함합니다.

## 1. 기존 명세 대비 주요 변경 사항

| 구분 | 변경 전 | 변경 후 |
| --- | --- | --- |
| 신규 OAuth 회원 | `PENDING` 생성 | `ACTIVE` 회원 생성 및 `onboardingStatus=NOT_STARTED` |
| 가입 완료 API | `REG-001 POST /api/v1/member-registrations` | 제거 |
| 온보딩 API | 없음 | `ONBOARDING-001 PATCH /api/v1/members/me/onboarding` |
| 지원공고 | `CAREER_DOCUMENTS.documentType=JOB_POSTING` | 독립된 `JOB_POSTINGS` 리소스 |
| 지원공고 입력 | 파일 중심 | 사용자가 제공한 `FILE` 또는 `TEXT` |
| 지원공고 URL | 후보 범위에 포함될 수 있었음 | 수집·크롤링·스크래핑하지 않음 |
| 언어 설정 | 세션 요청에 언어 포함 | 한국어 고정, 언어 필드 제거 |
| AI 대기 상태 | `PENDING` | `QUEUED` |
| 음성 프로필 | MVP 포함 여부 미확정 | 이번 MVP 구현 대상 |
| 음성 동의 | 추후 정책 | 온보딩 필수 동의와 분리된 기능 이용 동의 |
| 음성 처리 | 후보 수준 | 샘플 업로드, 비동기 복제, 상태 조회, 삭제까지 구현 |

### 1.1 명시적 제외 사항

- 회원 상태로서의 `PENDING`
- `REG-001` 및 `/api/v1/member-registrations`
- 지원공고 URL 수집, 외부 사이트 크롤링·스크래핑
- 사용자가 입력한 스크립트 또는 텍스트의 서버 실행
- `CAREER_DOCUMENTS`의 `JOB_POSTING` 문서 유형
- 면접 언어 선택 기능

## 2. 백엔드가 담당하는 핵심 작업

- OAuth 로그인, 신규 회원 자동 생성, 인증정보 발급·갱신·로그아웃
- 계정 상태와 온보딩 진행 상태의 분리 관리
- 최신 필수 법률 문서 제공 및 온보딩 동의 기록
- 이력서·선택 자기소개서 파일 저장과 처리 상태 관리
- 지원공고 파일 또는 일반 텍스트 저장, 텍스트 추출과 구조화 상태 관리
- 지원공고의 회사명·직무·주요 업무·자격요건 등 사용자 확인값 관리
- 면접 설정, 질문 순서, 답변 제출, 면접 진행 상태 관리
- 답변 영상·음성 파일 저장 및 AI 서버 전달
- 문서 파싱, 지원공고 파싱, STT·CV·발화·내용 분석 작업 요청과 결과 저장
- 음성정보 별도 동의 확인, 음성 샘플 저장, 음성 복제 작업 요청·상태·삭제 관리
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
| 지원공고 텍스트 | 일반 문자열로만 저장·분석하며 코드로 실행하지 않음 |

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
| 답변 | `QUESTION_READY`, `ANSWER_UPLOADED`, `ANALYZING`, `PARTIAL`, `READY`, `FAILED` | 질문 준비부터 답변 처리 완료까지의 상태 |
| 분석 작업 | `QUEUED`, `PROCESSING`, `PARTIAL`, `COMPLETED`, `FAILED` | 대기, 처리 중, 일부 완료, 전체 완료, 실패 |
| 음성 프로필 | `QUEUED`, `PROCESSING`, `READY`, `FAILED`, `DELETING` | 생성 대기, 생성 중, 사용 가능, 생성 실패, 삭제 중 |

## 4. 전체 API 목록

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
| ONBOARDING-001 | PATCH | `/api/v1/members/me/onboarding` | 내 온보딩 완료 처리 | 필요 | 최신 필수 문서 동의·고지 확인 목록 | `onboardingStatus=COMPLETED`, `nextAction` | 최신 필수 조건 검증, 법률 기록 저장, 온보딩 완료 처리 |
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

`documentType`은 다음 두 값만 사용합니다.

- `RESUME`
- `COVER_LETTER`

지원공고는 `CAREER_DOCUMENTS`에 저장하지 않고 `JOB-001~005`로 관리합니다.

### 4.3 지원공고

| ID | Method | URI | 기능 | Content-Type | 프론트 요청 | 주요 응답 | 백엔드 역할 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| JOB-001 | POST | `/api/v1/job-postings` | 지원공고 등록 | 파일: `multipart/form-data`, 텍스트: `application/json` | `inputType`, 파일 또는 `rawText` | `jobPostingId`, `processingStatus` | 원본 저장, 소유권 연결, 텍스트 추출·구조화 시작 |
| JOB-002 | GET | `/api/v1/job-postings` | 내 지원공고 목록 | 해당 없음 | `processingStatus`, `page`, `size` | 지원공고 목록 | 현재 사용자의 지원공고만 조회 |
| JOB-003 | GET | `/api/v1/job-postings/{jobPostingId}` | 지원공고 상세 조회 | 해당 없음 | `jobPostingId` | 원본 메타데이터, 추출·구조화 결과 | 소유권 확인 후 처리 상태와 지원정보 제공 |
| JOB-004 | PATCH | `/api/v1/job-postings/{jobPostingId}` | 지원공고 구조화 정보 수정 | `application/json` | 회사·직무·공고 항목 | 수정된 지원정보 | AI 추출 결과 또는 직접 입력값을 사용자 확인값으로 수정 |
| JOB-005 | DELETE | `/api/v1/job-postings/{jobPostingId}` | 지원공고 삭제 | 해당 없음 | `jobPostingId` | 없음 | DB 기록과 저장 파일 삭제, 사용 중 공고 삭제 제한 |

#### 입력 유형

| `inputType` | 입력 방식 | 처리 기준 |
| --- | --- | --- |
| `FILE` | 사용자가 지원공고 파일 업로드 | 파일을 저장하고 텍스트 추출 후 구조화 |
| `TEXT` | 사용자가 지원공고 내용을 붙여넣기 | `rawText`를 일반 문자열로 저장하고 구조화 |

`SCRIPT`라는 입력 유형은 사용하지 않습니다. 사용자가 입력한 내용은 실행 가능한 코드가 아니라 일반 텍스트 `TEXT`로 취급합니다.

#### JOB-001 파일 요청 예시

```text
Content-Type: multipart/form-data

inputType: FILE
file: 지원공고 파일
```

#### JOB-001 텍스트 요청 예시

```json
{
  "inputType": "TEXT",
  "rawText": "회사명: FaceFit ... 주요 업무: ... 자격요건: ..."
}
```

#### JOB-004 수정 가능 필드

필수 확인 항목:

- `companyName`
- `targetRole`
- `mainResponsibilities`
- `qualifications`

선택 항목:

- `preferredQualifications`
- `technologiesTools`
- `coreCompetencies`
- `companyBusinessIntro`

지원공고 등록 직후에는 구조화 필드가 비어 있을 수 있습니다. 면접 세션을 생성하기 전에는 처리 상태가 `READY`이고 네 개의 필수 확인 항목이 모두 존재해야 합니다.

### 4.4 면접 설정·진행

| ID | Method | URI | 기능 | 프론트 요청 | 주요 응답 | 백엔드 역할 | AI 연동 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SESSION-001 | POST | `/api/v1/interview-sessions` | 면접 세션 생성 | `resumeDocumentId`, `coverLetterDocumentId` 선택, `jobPostingId`, `persona`, `difficulty` | `sessionId`, `status=DRAFT` | 문서·공고 소유권과 준비 상태 검증, 지원정보 스냅샷 저장 | 없음 |
| SESSION-002 | GET | `/api/v1/interview-sessions/{sessionId}` | 면접 세션 조회 | `sessionId` | 설정, 지원정보 스냅샷, 진행 상태, 현재 질문 순서 | 본인 세션인지 확인 후 현재 상태 제공 | 없음 |
| SESSION-003 | PATCH | `/api/v1/interview-sessions/{sessionId}` | 면접 설정 수정 | 변경할 문서·공고·면접관·난이도 | 수정된 설정 | `DRAFT` 상태에서만 설정 수정, 공고 변경 시 스냅샷 갱신 | 없음 |
| SESSION-004 | POST | `/api/v1/interview-sessions/{sessionId}/start` | 면접 시작 | `sessionId` | 첫 질문, 질문 순서, `IN_PROGRESS` | 시작 조건 확인, 첫 질문 저장, 세션 시작 | 첫 질문 생성 요청 |
| SESSION-005 | POST | `/api/v1/interview-sessions/{sessionId}/completion` | 면접 종료 | `completionType` | `analysisJobId`, `status=ANALYZING` | 답변 제출 완료 확인, 세션 종료, 최종 분석 시작 | 최종 분석·리포트 생성 요청 |
| QUESTION-001 | GET | `/api/v1/interview-sessions/{sessionId}/questions/current` | 현재 질문 조회 | `sessionId` | 질문 ID, 내용, 의도, 순서, 유형 | 세션의 현재 질문 제공 | 없음 |

`SESSION-001`은 별도 언어 값을 받지 않습니다. 한국어 면접과 한국어 STT를 기본으로 사용합니다.

지원공고의 구조화 정보는 면접 세션 생성 시점에 세션 스냅샷으로 복사합니다. 이후 지원공고가 수정되거나 삭제되더라도 이미 진행된 면접의 기준 데이터는 변경하지 않습니다.

`completionType` 초안 값은 다음과 같습니다.

- `COMPLETED`
- `USER_INTERRUPTED`

중단한 면접의 분석 제공 범위는 추후 확정합니다.

### 4.5 답변 제출·처리

| ID | Method | URI | 기능 | 프론트 요청 | 주요 응답 | 백엔드 역할 | AI 연동 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ANSWER-001 | POST | `/api/v1/interview-sessions/{sessionId}/answers` | 답변 클립 제출 | `questionId`, `file`, `recordedDurationSec`, `endedBy` | `answerId`, `answerStatus`, `nextQuestionStatus` | 파일 검증·저장, 질문과 답변 연결, 중복 제출 방지 | STT·답변 분석·다음 질문 생성 요청 |
| ANSWER-002 | GET | `/api/v1/interview-answers/{answerId}` | 답변 처리 상태 조회 | `answerId` | 처리 상태, 전사문, 다음 질문 준비 여부 | 본인 답변 확인, AI 처리 결과와 다음 질문 상태 제공 | 없음 |

`endedBy` 초안 값은 다음과 같습니다.

- `USER_BUTTON`
- `SILENCE_DETECTED`

침묵 감지는 프론트엔드에서 수행하고 백엔드는 결과만 전달받습니다.

#### ANSWER-001 요청 예시

```text
Content-Type: multipart/form-data

questionId: 질문 UUID
file: 답변 영상 또는 음성 포함 영상
recordedDurationSec: 72
endedBy: USER_BUTTON
```

#### ANSWER-002 주요 응답 예시

```json
{
  "answerId": "answer-uuid",
  "status": "READY",
  "transcript": "지원한 직무에서 가장 중요하다고 생각하는 역량은...",
  "nextQuestionReady": true,
  "nextQuestionId": "question-uuid"
}
```

### 4.6 분석·리포트·마이페이지

| ID | Method | URI | 기능 | 프론트 요청 | 주요 응답 | 백엔드 역할 | AI 연동 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ANALYSIS-001 | GET | `/api/v1/interview-sessions/{sessionId}/analysis-status` | 분석 진행 상태 조회 | `sessionId` | 전체 상태, 단계별 상태, 진행률, 실패 단계 | 여러 AI 작업 상태를 한 화면용 상태로 통합 | 없음 |
| REPORT-001 | GET | `/api/v1/interview-sessions/{sessionId}/report` | 면접 종합 리포트 조회 | `sessionId` | 종합 점수, 평가 축 결과, 질문별 피드백, 모범답변, 역질문 | 완료된 분석 결과를 화면 구조에 맞게 조합 | 없음 |
| HISTORY-001 | GET | `/api/v1/members/me/interview-sessions` | 내 면접 이력 조회 | `status`, `page`, `size` | 기업, 직무, 완료일, 점수, 리포트 ID | 현재 사용자의 면접 목록 제공 | 없음 |
| GROWTH-001 | GET | `/api/v1/members/me/growth` | 회차별 성장 추이 조회 | `limit`, `from`, `to` | 회차별 종합·평가 축 점수 | 완료된 리포트 점수를 시간순으로 집계 | 없음 |

#### 분석 상태 응답 예시

```json
{
  "sessionId": "session-uuid",
  "status": "PROCESSING",
  "progress": 60,
  "steps": [
    { "type": "STT", "status": "COMPLETED" },
    { "type": "CV", "status": "PROCESSING" },
    { "type": "SPEECH", "status": "COMPLETED" },
    { "type": "CONTENT", "status": "PROCESSING" },
    { "type": "REPORT", "status": "QUEUED" }
  ]
}
```

#### 리포트 응답 주요 구조

```json
{
  "sessionId": "session-uuid",
  "overallScore": 82,
  "summary": "답변 내용은 구체적이지만 시선 유지와 말의 속도를 보완하면 좋습니다.",
  "axisScores": {
    "gaze": 78,
    "speech": 75,
    "posture": 86,
    "content": 89
  },
  "questionFeedback": [],
  "recommendedQuestions": [],
  "avoidQuestions": []
}
```

초기 구현에서는 분석 결과·질문별 피드백·모범답변을 별도 API로 분리하지 않고 `REPORT-001`에 포함합니다. 응답 크기 또는 화면 호출 시점이 달라질 때 분리를 검토합니다.

### 4.7 음성 클론 — 이번 MVP 구현 범위

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

음성 클론 생성 후 실제 면접 음성에 적용하는 시점과 AI 내부 합성 방식은 AI 담당자와의 내부 연동 규격에서 확정합니다. 현재 공개 API는 승인된 `VOICE-001~003`을 유지하며 새로운 Method·URI를 임의로 추가하지 않습니다.

## 5. 지원공고 입력·처리 흐름

### 5.1 파일 입력

```text
JOB-001 파일 업로드
→ 파일 검증 및 비공개 저장
→ processingStatus=PROCESSING
→ AI 또는 문서 파서에 텍스트 추출·구조화 요청
→ 성공 시 processingStatus=READY
→ JOB-003 결과 조회
→ 필요한 경우 JOB-004로 사용자 수정
→ SESSION-001에서 jobPostingId 사용
```

### 5.2 텍스트 입력

```text
JOB-001 rawText 등록
→ 일반 문자열로 저장
→ 구조화 처리
→ 성공 시 processingStatus=READY
→ JOB-003 결과 조회
→ 필요한 경우 JOB-004로 사용자 수정
→ SESSION-001에서 jobPostingId 사용
```

### 5.3 보안 기준

- 업로드된 지원공고 파일은 공개 URL로 노출하지 않습니다.
- 확장자만 믿지 않고 MIME 타입과 실제 파일 형식을 검증합니다.
- 텍스트에 HTML·JavaScript·명령문이 포함되어도 실행하지 않습니다.
- 프론트 출력 시 HTML 이스케이프 또는 안전한 텍스트 렌더링을 적용합니다.
- 파일·텍스트·추출 결과는 등록한 회원만 접근할 수 있습니다.
- 면접 세션에서 사용 중인 지원공고의 삭제 허용 방식은 구현 전에 확정합니다.

## 6. 백엔드와 AI 서버의 내부 연동 경계

AI 모델이 어떻게 분석하는지는 AI 담당자가 결정합니다. 백엔드는 입력을 전달하고 작업 상태와 결과를 받아 저장합니다.

| 내부 기능 | 호출 시점 | 백엔드가 전달할 값 | 백엔드가 받아야 할 값 | 백엔드 후속 처리 |
| --- | --- | --- | --- | --- |
| 경력 문서 처리 | DOC-001 등록 후 | `documentId`, 파일 참조, 문서 종류 | 추출 텍스트, 처리 상태, 오류 | 문서 상태와 추출 결과 저장 |
| 지원공고 처리 | JOB-001 등록 후 | `jobPostingId`, 파일 참조 또는 `rawText` | 추출 텍스트, 구조화 필드, 처리 상태, 오류 | 지원공고 처리 상태와 구조화 결과 저장 |
| 질문 생성 | 면접 시작·답변 처리 후 | 세션 스냅샷, 문서 텍스트, 이전 질문·답변 | 질문 내용, 질문 유형, 부모 질문 ID | 질문 순서와 현재 질문 저장 |
| STT | 답변 업로드 후 | `answerId`, 미디어 참조 | 한국어 전사문, 시간 정보, 처리 상태 | 답변에 전사 결과 연결 |
| CV 분석 | 답변 업로드 또는 면접 종료 후 | `answerId`, 영상 참조 | 시선·자세 측정값, 처리 상태 | 답변별 분석 결과 저장 |
| 발화·내용 분석 | STT 완료 후 | 질문, 전사문, 답변 시간, 문서·지원공고 맥락 | 발화 지표, 내용 점수, 근거, 개선안 | 답변별 점수와 피드백 저장 |
| 리포트 생성 | 모든 필수 분석 완료 후 | 질문·답변·평가 축 분석 결과 | 종합 요약, 질문별 피드백, 모범답변, 역질문 | 최종 리포트 저장, 세션 `COMPLETED` 전환 |
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

## 7. 최소 오류 코드

| HTTP 상태 | 오류 코드 | 사용 상황 |
| --- | --- | --- |
| 400 | `VALIDATION_FAILED` | 필수값 누락·형식 오류 |
| 400 | `UNSUPPORTED_INPUT_TYPE` | 지원공고 입력 유형이 `FILE`, `TEXT`가 아님 |
| 401 | `AUTH_REQUIRED` | 로그인 필요·인증 만료 |
| 403 | `ACCESS_DENIED` | 회원 상태 또는 권한 부족 |
| 403 | `ONBOARDING_REQUIRED` | 온보딩 완료가 필요한 서비스 API 호출 |
| 403 | `VOICE_CONSENT_REQUIRED` | 음성 클론에 필요한 별도 동의가 없거나 철회됨 |
| 404 | `RESOURCE_NOT_FOUND` | 리소스 없음 또는 본인 소유가 아님 |
| 409 | `INVALID_STATE` | 현재 상태에서 실행할 수 없는 요청 |
| 409 | `RESOURCE_NOT_READY` | 문서 또는 지원공고 처리가 완료되지 않음 |
| 409 | `VOICE_PROFILE_NOT_READY` | 음성 클론 생성이 완료되지 않았거나 삭제 중 |
| 409 | `DUPLICATE_REQUEST` | 답변·면접 시작 등 중복 요청 |
| 413 | `FILE_TOO_LARGE` | 허용 용량 초과 |
| 415 | `FILE_TYPE_NOT_SUPPORTED` | 허용하지 않는 파일 형식 |
| 500 | `INTERNAL_ERROR` | 백엔드 내부 오류 |
| 502 | `AI_SERVICE_ERROR` | AI 서버 호출 실패 |

AI 처리 실패는 가능하면 API 전체 오류로 끝내지 않고 `FAILED` 상태와 실패 단계를 저장하여 프론트엔드가 상태 조회 화면에서 확인할 수 있게 합니다.

## 8. 프론트엔드 협업 기준

| 화면 | 프론트가 호출할 핵심 API | 프론트 표시 기준 |
| --- | --- | --- |
| 로그인 | AUTH-001~003, AUTH-006 | `memberStatus`, `onboardingStatus`, `nextAction` |
| 온보딩 | LEGAL-001~002, ONBOARDING-001 | 최신 필수 문서, 필요 행위, 완료 상태 |
| 문서 등록 | DOC-001~003 | 이력서·자기소개서 처리 상태 |
| 지원공고 등록 | JOB-001~004 | 입력 유형, 처리 상태, 추출·구조화 결과 |
| 면접 설정 | DOC-002~003, JOB-002~004, SESSION-001~003 | 문서·지원공고 `READY`, 세션 `DRAFT` |
| 면접 진행 | SESSION-004, QUESTION-001, ANSWER-001~002 | 현재 질문, 답변 처리, 다음 질문 준비 여부 |
| 분석 중 | SESSION-005, ANALYSIS-001 | 분석 전체 상태와 단계별 상태 |
| 리포트 | REPORT-001 | `COMPLETED` 리포트 데이터 |
| 마이페이지 | MEMBER-001, HISTORY-001, GROWTH-001 | 프로필, 면접 목록, 회차별 점수 |
| 음성 클론 | LEGAL-001~002, VOICE-001~003 | 별도 동의, 샘플 등록, 생성 상태, 삭제 상태 |

## 9. 구현 우선순위

1. 인증·회원 자동 생성: AUTH-001~006
2. 법률 문서·온보딩·프로필: LEGAL-001~002, ONBOARDING-001, MEMBER-001
3. 이력서·자기소개서: DOC-001~004
4. 지원공고 파일·텍스트: JOB-001~005
5. 면접 설정: SESSION-001~003
6. 면접 진행: SESSION-004~005, QUESTION-001, ANSWER-001~002
7. 분석·결과: ANALYSIS-001, REPORT-001
8. 마이페이지: HISTORY-001, GROWTH-001
9. 음성 클론: LEGAL-001~002, VOICE-001~003
10. 전체 보안·소유권·삭제·AI 연동 통합 검증

## 10. 구현 전에 추가 확정할 항목

- OAuth 제공자별 운영 설정과 토큰·쿠키 방식
- 온보딩에 법률 문서 외 추가 프로필 입력을 포함할지 여부
- 지원공고 업로드 허용 형식과 최대 용량
- 이력서·자기소개서·답변 영상의 허용 형식과 최대 용량
- 지원공고 파일에서 지원정보를 추출하는 파서 또는 AI 연동 방식
- 지원공고 처리 실패·재시도 방식
- 면접 질문 개수, 제한 시간, 중단 세션 재개 여부
- 답변 중복 제출과 업로드 실패 재시도 방식
- AI 서버 호출 URI, 인증 방식, 타임아웃, 결과 전달 방식
- 일부 분석만 성공했을 때 리포트 제공 여부
- 점수 범위와 소수점 처리 방식
- 파일·원문·전사문·분석 결과의 보관 및 삭제 기간
- 탈퇴 회원 데이터의 보관·삭제 방식
- 음성 샘플 허용 형식·최소/최대 길이·최대 용량
- 음성 샘플·미리듣기·외부 복제 모델의 보관기간과 삭제 완료 기준
- 동의 철회 시 즉시 사용 차단과 물리 삭제 처리 순서
- 음성 클론 AI 서버 호출 URI, 인증, 타임아웃, 생성·삭제 Callback 방식
- 복제 음성을 실제 면접 음성에 적용하는 시점과 내부 합성 방식

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
