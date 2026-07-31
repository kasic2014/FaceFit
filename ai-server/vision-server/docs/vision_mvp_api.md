# Face-Fit Vision MVP API

단일 세션 Baseline 대비 상대 분석 결과를 제공하는 AI/Vision 전용 HTTP
계약이다. Spring Boot, React, 채용 평가, 점수, 합격 가능성, 성격 및 심리
추론은 이 서버의 범위가 아니다.

## Runtime

```powershell
cd ai-server\vision-server
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

환경변수는 `.env.example`을 참고한다. `VISION_API_ALLOWED_ORIGINS`의 기본값은
빈 목록이며 `*`는 허용되지 않는다. 운영 환경에서는 Swagger UI가 기본적으로
비활성화된다.

## Endpoint

| Method | Path | 설명 |
|---|---|---|
| GET | `/health` | 프로세스 생존 확인 |
| GET | `/ready` | Stage 22 service, output 및 Job 저장소 준비 상태 |
| POST | `/api/v1/vision/jobs` | 피드백 조회 또는 재생성 Job 생성 |
| GET | `/api/v1/vision/jobs/{job_id}` | UUID Job 상태 조회 |
| GET | `/api/v1/vision/sessions/{session_id}/feedback` | Stage 22 공개 피드백 조회 |
| GET | `/openapi.json` | OpenAPI 계약 |

`sessionId`는 `SES_`와 6자리 숫자로만 구성된다. API는 파일 경로,
Participant ID, Consent, Metadata 또는 Rater ID를 입력받지 않는다.

### Job 생성

```json
{
  "sessionId": "SES_000001",
  "analysisMode": "SINGLE_SESSION_BASELINE_RELATIVE_MVP",
  "forceRebuild": false
}
```

`forceRebuild=false`는 strict-load한 기존 Stage 22 공개 계약을 재사용한다.
`forceRebuild=true`는 CLI나 전체 영상 파이프라인을 호출하지 않고 Stage 22
service 함수로 피드백 계약만 재생성한다.

Idempotency 키는 `sessionId`, `analysisMode`, `forceRebuild` 조합이다.
동일한 실행 중 Job을 재사용하며, 성공한 `forceRebuild=false` 요청도 기존
Job을 재사용한다. `forceRebuild=true`의 완료 Job은 후속 요청에서 재사용하지
않는다.

Job 상태는 `QUEUED`, `RUNNING`, `SUCCEEDED`,
`SUCCEEDED_WITH_LIMITATIONS`, `FAILED`만 허용한다. Job JSON은
`data/output/vision_api/jobs/`에 atomic strict JSON으로 저장되며 Git에서
제외된다.

### 점수 미지원 계약

```json
{
  "scores": null,
  "scoringUnavailableReasons": [
    "SCORING_NOT_AVAILABLE_SINGLE_SESSION_MVP",
    "THRESHOLD_EVIDENCE_NOT_APPROVED"
  ]
}
```

Head Pose 누락값은 보간하거나 임의 값으로 대체하지 않는다.

## 오류 계약

```json
{
  "code": "SESSION_NOT_FOUND",
  "message": "요청한 분석 세션을 찾을 수 없습니다.",
  "requestId": "비식별 UUID",
  "details": []
}
```

오류 코드는 `VALIDATION_ERROR`, `SESSION_NOT_FOUND`, `JOB_NOT_FOUND`,
`RESULT_NOT_READY`, `UNSUPPORTED_ANALYSIS_MODE`,
`INPUT_ARTIFACTS_MISSING`, `FEEDBACK_BUILD_FAILED`,
`DEPENDENCY_UNAVAILABLE`, `JOB_STORAGE_ERROR`,
`INTERNAL_SERVER_ERROR`로 제한한다. Stack trace, 내부 예외 문자열 및 절대
경로는 응답에 포함하지 않는다.

## 검증

FastAPI dependency가 설치된 뒤 다음을 실행한다.

```powershell
.venv\Scripts\python.exe -m unittest runtime_tests.test_vision_mvp_api_runtime_stage23 -v
.venv\Scripts\python.exe scripts\smoke_vision_mvp_uvicorn.py --session-id SES_000001
docker compose -f ..\..\docker-compose.local.yml config
```

Runtime smoke script는 Uvicorn을 실제로 기동하고 필수 endpoint를 호출한 뒤
프로세스를 종료하며 포트가 남아 있지 않은지 확인한다.
