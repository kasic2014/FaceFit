# Backend integration guide

## 1. 사전 확인

두 서비스에 대해 `GET /health`와 `GET /ready`를 호출한다. `/health`는 process liveness이고 `/ready`는 저장소·queue·pipeline resolver 준비 상태다. 준비 실패를 Session 결과 실패와 혼동하지 않는다.

필수 공개 경로:

- Vision `POST /api/v1/vision/jobs`
- Vision `GET /api/v1/vision/jobs/{job_id}`
- Vision `GET /api/v1/vision/sessions/{session_id}/feedback`
- Analysis `POST /api/v1/analysis/jobs`
- Analysis `GET /api/v1/analysis/jobs/{job_id}`
- Analysis `GET /api/v1/analysis/sessions/{session_id}/transcription`
- Analysis `GET /api/v1/analysis/sessions/{session_id}/speech-characteristics`

## 2. 언어 중립 DTO

Job request:

- `sessionId: string`
- Vision `analysisMode: enum`
- Analysis `pipeline: enum`
- `forceRebuild: boolean`

Job response 공통:

- `jobId: UUID string`
- `sessionId: string`
- `status: enum`
- `createdAt`, `startedAt`, `completedAt: UTC timestamp or null`
- `resultAvailable: boolean`
- `warnings: Warning[]`
- `error: JobError or null`

Analysis Job에는 `queuedAt`, `updatedAt`, `queueWaitMs`, `executionDurationMs`, `totalDurationMs`가 추가된다. 숫자 duration은 millisecond이며 timestamp string과 혼합하지 않는다.

Warning DTO:

- `source: VISION | TRANSCRIPTION | SPEECH | INTEGRATION`
- `code: string`
- `message: string`
- `answerId: string or null`
- `reviewRequired: boolean`

Error DTO:

- API error: `code`, `message`, `requestId`, `details`
- Integration error: `source`, `code`, `message`, `retryable`

## 3. 권장 orchestration 의사코드

```text
validate sessionId
visionJob = POST Vision(forceRebuild=false)
analysisJob = POST Analysis(forceRebuild=false)
persist both opaque job IDs and X-Request-ID values

poll both jobs independently with bounded deadline
if Vision succeeded: fetch feedback
if Analysis succeeded: fetch transcription and speech characteristics

validate all returned sessionId values
validate Answer sets exactly
validate [start, end) intervals in milliseconds
preserve original sourceStatus
deduplicate warnings by source + code + answerId
return integrated result or partial result
```

한 Job 실패가 다른 정상 결과를 삭제하게 만들지 않는다. 다만 Session, Answer 또는 timestamp 필수 정합성이 깨지면 통합 성공으로 응답하면 안 된다.

## 4. SES_000001 공식 구간

| Answer | Start ms | End ms | Duration ms |
|---|---:|---:|---:|
| `ANS_000001` | 11000 | 50000 | 39000 |
| `ANS_000002` | 51000 | 107000 | 56000 |
| `ANS_000003` | 108000 | 160000 | 52000 |
| `ANS_000004` | 161000 | 192000 | 31000 |

Timestamp를 초나 frame 번호로 임의 변환해 원본 필드에 다시 저장하지 않는다. 표시 변환값이 필요하면 별도 presentation 필드를 사용한다.

## 5. 결과 구성

정상적인 SES_000001 결과는 Vision Answer 4, STT Answer 4, Segment 27, Word 307, Speech Answer 4, Filler Candidate 1, Pitch 가용 Answer 4다. 27은 Segment 수이고 307은 Word 수다.

최종 상태는 `INTEGRATED_READY_WITH_WARNINGS`다. Head Pose, STT 경계, upstream transcription, filler review 및 GPU 제한은 오류로 숨기지 않고 warning 또는 limitation으로 전달한다.

## 6. Idempotency

일반 사용자 retry는 동일 payload와 `forceRebuild=false`를 사용한다. 서버는 진행 중이거나 정상 완료된 Job을 재사용할 수 있다. Job ID가 opaque하므로 Backend가 자체 Job ID를 합성하지 않는다. `forceRebuild=true`는 자동 retry 수단이 아니다.

## 7. Request ID

각 응답의 `X-Request-ID`를 log correlation용으로 저장한다. Analysis는 유효한 요청 header를 보존할 수 있고 Vision은 자체 UUID를 발급한다. Request ID를 인증·인가 식별자로 사용하지 않는다.
