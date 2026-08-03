# Polling and retry policy

## 기본값

- 초기 polling 간격: 250~500ms
- 장시간 Job: bounded exponential backoff 사용 가능
- 최대 대기시간: 서비스 운영 정책으로 명시하고 반드시 deadline 적용
- terminal 상태 도달 즉시 polling 종료
- Vision과 Analysis는 독립적으로 polling

Stage 28 검증 도구의 기본은 250ms, 최대 120초다. Backend는 자신의 SLA에 따라 상한을 정하되 무한 polling을 구현하면 안 된다.

## Terminal 상태

| 서비스 | 성공 | 경고 포함 성공 | 실패 |
|---|---|---|---|
| Vision | `SUCCEEDED` | `SUCCEEDED_WITH_LIMITATIONS` | `FAILED` |
| Analysis | `SUCCEEDED` | `SUCCEEDED_WITH_WARNINGS` | `FAILED` |

`QUEUED`와 `RUNNING`만 비terminal이다.

## HTTP 처리표

| HTTP | 대표 코드 | 자동 retry | Backend 권장 처리 | 사용자 메시지 |
|---:|---|---|---|---|
| 404 | `JOB_NOT_FOUND` | 아니오 | 저장한 Job ID와 요청 흐름 확인 | 작업을 찾을 수 없음 |
| 404 | `SESSION_NOT_FOUND` | 아니오 | Session 생성·등록 흐름 확인 | 세션을 찾을 수 없음 |
| 409 | `RESULT_NOT_READY` | 제한적 | terminal 확인 후 짧은 bounded retry | 결과 준비 중 |
| 409 | `INVALID_JOB_STATE_TRANSITION` | 아니오 | 서버 운영 오류로 기록 | 작업 상태 오류 |
| 422 | `VALIDATION_ERROR` | 아니오 | payload와 ID 형식 수정 | 요청 형식 오류 |
| 422 | `UNSUPPORTED_ANALYSIS_MODE` | 아니오 | 지원 enum 사용 | 지원하지 않는 분석 모드 |
| 422 | `UNSUPPORTED_PIPELINE` | 아니오 | 지원 enum 사용 | 지원하지 않는 분석 파이프라인 |
| 429/503 | `JOB_QUEUE_FULL` | 예 | jitter를 포함한 bounded backoff | 분석 요청이 많아 재시도 필요 |
| 503 | `DEPENDENCY_UNAVAILABLE` | 운영 정책 | dependency 상태 확인 후 제한적 retry | 분석 기능 일시 사용 불가 |
| 500 | `*_FAILED` | 무한 retry 금지 | requestId와 code 기록 후 운영 확인 | 분석 처리 실패 |

## Retry 규칙

1. 동일 retry는 `forceRebuild=false`를 유지한다.
2. network timeout과 5xx는 최대 횟수와 전체 deadline을 함께 제한한다.
3. validation, unsupported, not-found 오류는 payload나 상태가 바뀌지 않는 한 retry하지 않는다.
4. `FAILED` Job을 자동으로 성공 처리하거나 기존 결과 파일 존재만으로 승격하지 않는다.
5. retry마다 원본 request ID와 새 response request ID를 함께 기록한다.
6. circuit breaker 또는 queue 보호 정책을 적용할 수 있으나 AI status enum을 변경하지 않는다.

## Partial 결과

한 컴포넌트가 실패하더라도 다른 컴포넌트가 사용 가능하면 해당 결과를 보존한다. Backend가 partial 응답을 허용하지 않는 제품 정책이라면 사용자 응답은 실패로 변환할 수 있지만, 내부 기록에는 원본 component status와 오류를 남긴다.
