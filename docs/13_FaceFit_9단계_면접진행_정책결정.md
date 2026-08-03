# FaceFit 9단계 면접 진행 정책 결정

| 항목 | 내용 |
| --- | --- |
| 상태 | 확정 |
| 확정일 | 2026-07-30 |
| 범위 | SESSION-004~005, QUESTION-001, ANSWER-001~002 |
| 우선순위 | 이 문서의 계약은 기존 v0.3 명세와 9단계 초안의 충돌 부분보다 우선 |

## 질문 생성과 세션 시작

- `SESSION-004`는 `Idempotency-Key`가 필요한 비동기 접수 API다.
- 최초 요청은 질문 생성 작업만 `QUEUED`로 등록하고 `202 Accepted`를
  반환한다.
- 질문이 생성되기 전 세션은 `DRAFT`, `startedAt=null`을 유지한다.
- 질문은 총 10개이며 모두 필수다. 순서는 1부터 10까지 연속이다.
- Worker가 응답 전체를 검증하고 질문 10개를 저장한 트랜잭션에서만
  세션을 `IN_PROGRESS`로 전환한다.
- 외부 응답이 잘못되면 부분 질문을 저장하지 않는다.
- 최종 실패한 세션은 `DRAFT`를 유지하며 새 멱등성 키로 재시작할 수 있다.

질문 유형과 개수는 다음과 같다.

| 유형 | 개수 |
| --- | ---: |
| `INTRODUCTION` | 1 |
| `EXPERIENCE` | 3 |
| `JOB_ROLE` | 3 |
| `BEHAVIORAL` | 2 |
| `CLOSING` | 1 |

질문 생성 요청과 응답은 `schemaVersion=1.0`,
`generationRequestId`, 한국어 locale, persona, difficulty, 질문 정책,
문서 추출문, 지원공고 스냅샷 8개 및 질문 10개 배열을 사용한다.
응답은 요청 ID 일치, 정확한 개수, 연속 순서, 허용 유형, 중복되지 않은
500자 이하의 비어 있지 않은 본문을 모두 만족해야 한다.

## 현재 질문

- 질문 생성 작업이 `QUEUED` 또는 `PROCESSING`이면 `202 Accepted`와
  `QUESTION_GENERATION_IN_PROGRESS` 상태를 반환한다.
- 최종 실패하면 `503 QUESTION_GENERATION_FAILED`를 반환하고 외부 오류
  전문은 숨긴다.
- `IN_PROGRESS`에서는 확정 답변이 없는 가장 낮은 순서의 Turn을 반환한다.
- 모든 질문에 답변했으면 `200`, `ALL_QUESTIONS_ANSWERED`,
  `canFinish=true`를 반환한다.
- 작업이 없는 `DRAFT` 또는 현재 질문을 제공할 수 없는 상태는
  `409 INVALID_STATE`다.

## 답변 미디어와 분석 작업

- MP4(`video/mp4`, `ftyp`)와 WebM(`video/webm`, EBML)만 허용한다.
- 영상·음성 스트림이 모두 있어야 하며 최대 200MB, 최대 300초다.
- 원본은 Private `interview-answers` bucket의 서버 생성 UUID 경로에
  저장한다.
- DB 확정 실패 시 방금 올린 객체를 보상 삭제한다.
- 답변 확정과 STT·CV·VOICE·CONTENT 작업 4개 등록은 하나의
  트랜잭션에서 처리한다.
- 개별 작업은 최대 3회 실행하며 재시도 간격은 2초와 10초다.
- timeout은 STT 120초, 나머지 분석과 질문 생성은 60초다.

## 멱등성과 동시성

- 시작·답변·종료 API는 8~64자 `Idempotency-Key`를 필수로 받는다.
- 허용 문자는 영문, 숫자, `.`, `_`, `:`, `-`다.
- 범위는 회원·HTTP Method·URI·키 조합이다.
- 같은 요청은 최초 결과를 재사용하고 내용이 다르면
  `IDEMPOTENCY_KEY_REUSED`, 처리 중이면
  `IDEMPOTENCY_REQUEST_IN_PROGRESS`다.
- Turn별 확정 답변은 하나이며 Turn 잠금과 DB UNIQUE를 함께 적용한다.
- Worker는 획득 토큰을 사용하고 토큰이 일치하는 실행만 결과를 반영한다.

## 면접 종료

- `NORMAL`은 질문 10개의 답변 미디어가 모두 확정된 경우에만
  `INTERVIEW_COMPLETED`로 전환한다.
- 답변별 분석 작업 상태는 `NORMAL` 종료를 막지 않는다.
- `USER_INTERRUPTED`는 미답변 상태에서도 `IN_PROGRESS → INTERRUPTED`를
  허용한다.
- 중단된 세션의 기존 답변·분석 작업은 유지하되 최종 분석·리포트 작업은
  만들지 않는다.
- 이번 단계에서는 `ANALYZING → COMPLETED`와 최종 리포트를 구현하지 않는다.

## 외부 연동 제외 범위

실제 AI·STT URI, 인증 헤더 및 외부 제공자 JSON은 아직 확정되지 않았다.
따라서 이번 단계는 내부 Port, 작업 영속화, Worker 획득·timeout·재시도,
테스트용 Fake만 구현한다. 운영 코드에는 가짜 질문·전사·분석 성공 결과를
넣지 않으며 실제 AI·STT E2E 성공은 완료 기준에서 제외한다.
