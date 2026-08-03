# Error and warning reference

오류 body는 stack trace나 내부 예외 문자열을 포함하지 않는다. Backend는 `code`를 분기 기준으로 사용하고 `message`는 사용자 노출 전에 제품 문구 정책을 적용한다.

## Vision errors

| Code | HTTP | Retry | Backend action |
|---|---:|---|---|
| `VALIDATION_ERROR` | 400/422 | No | ID와 payload 수정 |
| `SESSION_NOT_FOUND` | 404 | No | Session 등록 확인 |
| `JOB_NOT_FOUND` | 404 | No | 저장된 Job ID 확인 |
| `RESULT_NOT_READY` | 409 | Limited | terminal 상태 확인 후 bounded retry |
| `UNSUPPORTED_ANALYSIS_MODE` | 422 | No | 지원 mode 사용 |
| `INPUT_ARTIFACTS_MISSING` | 503 | Policy | 입력 준비 상태 확인 |
| `FEEDBACK_BUILD_FAILED` | 500 | No automatic loop | requestId로 운영 확인 |
| `DEPENDENCY_UNAVAILABLE` | 503 | Policy | readiness와 dependency 확인 |
| `JOB_STORAGE_ERROR` | 500 | No automatic loop | 저장소 운영 확인 |
| `INTERNAL_SERVER_ERROR` | 500 | Bounded | requestId 기록, 운영 확인 |

## Analysis errors

| Code | HTTP | Retry | Backend action |
|---|---:|---|---|
| `VALIDATION_ERROR` | 422 | No | ID와 payload 수정 |
| `SESSION_NOT_FOUND` | 404 | No | Session 입력 준비 확인 |
| `JOB_NOT_FOUND` | 404 | No | 저장된 Job ID 확인 |
| `RESULT_NOT_READY` | 409 | Limited | terminal 상태 확인 후 bounded retry |
| `UNSUPPORTED_PIPELINE` | 422 | No | 지원 pipeline 사용 |
| `INPUT_ARTIFACTS_MISSING` | 503 | Policy | Stage 24 입력 산출물 확인 |
| `TRANSCRIPTION_FAILED` | 500 | No automatic loop | STT 운영 확인 |
| `SPEECH_ANALYSIS_FAILED` | 500 | No automatic loop | Speech 운영 확인 |
| `DEPENDENCY_UNAVAILABLE` | 503 | Policy | 모델·FFmpeg·runtime 확인 |
| `JOB_STORAGE_ERROR` | 500 | No automatic loop | Job 저장소 확인 |
| `JOB_QUEUE_FULL` | 503 | Yes, bounded | jitter backoff |
| `INVALID_JOB_STATE_TRANSITION` | 409 | No | 상태 기록 감사 |
| `INTERNAL_SERVER_ERROR` | 500 | Bounded | requestId 기록, 운영 확인 |

## Integration errors

| Code | Retry | Backend action |
|---|---|---|
| `SESSION_ID_MISMATCH` | No | 필수 계약 실패 처리 |
| `ANSWER_SET_MISMATCH` | No | 누락·추가·중복 Answer 조사 |
| `ANSWER_INTERVAL_MISMATCH` | No | 공식 구간과 source 결과 비교 |
| `TIMESTAMP_OUT_OF_RANGE` | No | timestamp source 조사, 자동 clamp 금지 |
| `COMPONENT_RESULT_NOT_READY` | Limited | component terminal 상태 확인 |
| `COMPONENT_JOB_FAILED` | Policy | 다른 결과를 보존하고 partial 판단 |
| `COMPONENT_HTTP_ERROR` | Bounded | HTTP status와 retryable 확인 |
| `COMPONENT_RESPONSE_INVALID` | No | API·Schema compatibility 실패 처리 |
| `INTEGRATION_TIMEOUT` | Yes, bounded | 전체 deadline 이후 중단 |

## 주요 Warning과 limitation

| Code | Source | 의미 | Backend 처리 |
|---|---|---|---|
| `HEAD_POSE_PARTIAL_AVAILABILITY` | VISION | 일부 프레임 Head Pose 미측정 | 결과 유지, 제한 표시 |
| `SEGMENT_BOUNDARY_EXPANDED_TO_WORDS` | TRANSCRIPTION | Segment 경계를 word timestamp에 맞춤 | 결과 유지 |
| `UPSTREAM_TRANSCRIPTION_WARNING` | SPEECH | Speech가 경고 포함 STT를 사용 | 결과 유지, provenance 보존 |
| `FILLER_CANDIDATE_REVIEW_REQUIRED` | SPEECH | filler 자동 확정 불가 | `reviewRequired=true` 보존 |
| `ANALYSIS_DOCKER_GPU_FORCE_REBUILD_NOT_VERIFIED` | INTEGRATION | GPU 실제 강제 재전사 미검증 | 운영 limitation 표시 |

Warning은 오류가 아니다. 중복 제거 키는 `source + code + answerId`이며 서로 다른 source의 같은 code를 합치지 않는다.
