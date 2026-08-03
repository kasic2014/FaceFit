# Face-Fit AI Backend handoff

이 디렉터리는 Backend 담당자가 Vision 또는 Analysis 내부 구현을 읽지 않고도 면접 Session 처리 흐름을 구현할 수 있도록 제공하는 언어 중립 계약 패키지다. Java/Spring DTO나 HTTP Client 구현은 포함하지 않는다.

## 서비스 구성

| 서비스 | 기본 Host URL | 역할 |
|---|---|---|
| Vision | `http://127.0.0.1:8000` | 단일 Session 얼굴·양쪽 어깨 측정 및 제한사항 제공 |
| Analysis | `http://127.0.0.1:8002` | 한국어 STT와 측정 전용 발화 특성 제공 |
| Integration | Backend 또는 별도 orchestration 계층 | 두 Job과 세 결과를 검증·결합 |

Docker 내부 DNS는 `http://vision-server:8000`과 `http://analysis-server:8002`다.

## 식별자와 시간

- `sessionId`: `^SES_\d{6}$`
- `answerId`: `^ANS_\d{6}$`
- `jobId`: UUID
- `requestId`: 응답의 `X-Request-ID` 헤더 및 오류 body의 `requestId`
- Timestamp 단위: millisecond
- 답변 구간: `[start, end)`, start 포함·end 제외

Backend 저장 권장 필드는 `sessionId`, `visionJobId`, `analysisJobId`, `sourceStatus`, `normalizedStatus`, `requestId`, `createdAt`, `startedAt`, `completedAt`, `warnings`, `errors`다. 이 목록은 DTO 명세이며 Entity나 테이블 코드를 정의하지 않는다.

## 호출 순서

1. `POST /api/v1/vision/jobs`
2. `POST /api/v1/analysis/jobs`
3. 두 응답의 Job ID를 저장한다.
4. `GET /api/v1/vision/jobs/{job_id}`와 `GET /api/v1/analysis/jobs/{job_id}`를 독립적으로 polling한다.
5. 두 Job이 terminal 상태가 되면 결과를 조회한다.
6. `GET /api/v1/vision/sessions/{session_id}/feedback`
7. `GET /api/v1/analysis/sessions/{session_id}/transcription`
8. `GET /api/v1/analysis/sessions/{session_id}/speech-characteristics`
9. Session·Answer 집합·timestamp를 검증한다.
10. Warning과 Error를 보존하고 Backend 응답을 구성한다.

운영 확인용 endpoint는 두 서비스 공통 `GET /health`, `GET /ready`다.

## 기본 요청

Vision:

```json
{
  "sessionId": "SES_000001",
  "analysisMode": "SINGLE_SESSION_BASELINE_RELATIVE_MVP",
  "forceRebuild": false
}
```

Analysis:

```json
{
  "sessionId": "SES_000001",
  "pipeline": "STT_AND_SPEECH",
  "forceRebuild": false
}
```

일반 요청은 항상 `forceRebuild=false`를 사용한다. 같은 Session과 mode 또는 pipeline의 정상 Job은 재사용될 수 있다. `forceRebuild=true`는 관리자 또는 복구 작업에서 명시적으로 승인한 경우에만 사용한다. Analysis Docker GPU 강제 재전사는 아직 검증되지 않았으므로 무분별하게 호출하지 않는다.

## Job 상태

Vision: `QUEUED`, `RUNNING`, `SUCCEEDED`, `SUCCEEDED_WITH_LIMITATIONS`, `FAILED`

Analysis: `QUEUED`, `RUNNING`, `SUCCEEDED`, `SUCCEEDED_WITH_WARNINGS`, `FAILED`

통합 계층은 Vision `SUCCEEDED_WITH_LIMITATIONS`를 `SUCCEEDED_WITH_WARNINGS`로 정규화하지만 `sourceStatus`에는 원본 값을 보존한다. POST는 장시간 분석 완료를 기다리지 않고 Job을 즉시 반환할 수 있으므로 terminal 상태까지 polling해야 한다.

## 개인정보와 점수

- `FACEFIT_INTEGRATION_EXPOSE_TRANSCRIPT_TEXT=false`가 기본이다.
- 운영 Analysis는 `ANALYSIS_API_EXPOSE_TRANSCRIPT_TEXT=false`를 사용한다.
- 비노출 상태에서는 Answer·Segment·Word text가 `null`이고 count와 timestamp만 사용한다.
- Participant, consent, metadata, rater, 원본 파일명, 내부 경로, 모델 캐시 경로를 저장하거나 전달하지 않는다.
- `scoringAvailable=false`다. 승인된 threshold와 scoring evidence가 없으므로 Backend가 점수·등급·합격 확률을 만들면 안 된다.

## 현재 제한

- 단일 실제 Session 기반 MVP다.
- Head Pose는 일부 프레임에서만 가용하다.
- Filler는 후보이며 사람 검토가 필요하다.
- GPU Docker 실제 `forceRebuild` 전사는 미검증이다.
- 감정·성격·불안·자신감·합격 가능성을 추론하지 않는다.

자세한 구현 순서는 [Backend integration guide](docs/backend-integration-guide.md), retry 정책은 [Polling and retry policy](docs/polling-and-retry-policy.md), 코드 목록은 [Error and warning reference](docs/error-warning-reference.md)를 읽는다.

## 패키지 검증

```powershell
python ai-server/integration/handoff/scripts/export_ai_contracts.py
python ai-server/integration/handoff/scripts/validate_handoff_package.py
```

Export는 각 서버 app factory에서 OpenAPI를 생성해 필수 endpoint와 enum을 확인한다. 실제 Session 결과는 export하지 않는다. Validator는 필수 파일, Strict JSON, Schema, Example, endpoint, 상태, 코드 문서화, 개인정보, transcript 원문 및 금지 평가 필드를 확인한다.
