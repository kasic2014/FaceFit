# Face Fit Ncloud 면접 영상 저장소 전환

## 범위와 아키텍처

면접 답변 MP4/WebM 원본만 NAVER Cloud Platform Object Storage 비공개 버킷으로 이동한다. Supabase Auth·PostgreSQL과 `career-documents`, `job-postings`는 그대로 유지한다. 공개 `ANSWER-001`의 Method, URI, multipart 요청 및 응답은 변경하지 않는다.

```text
Client multipart
  -> Spring 소유권·세션·미디어 검증
  -> Ncloud Private Object Storage 업로드
  -> Supabase PostgreSQL에 영구 위치 저장
  -> Worker attempt 직전 Presigned GET URL 생성
  -> Python JSON 요청 및 제한 스트리밍 다운로드
  -> STT/CV 분석 후 Python 임시 파일 삭제
```

Ncloud Access Key와 Secret Key는 Spring Boot에만 둔다. Python에는 인증키를 전달하지 않는다.

## DB와 Flyway

신규 마이그레이션은 `V8__migrate_interview_answer_media_location.sql` 하나이며 V1~V7은 수정하지 않는다. 기존 `storage_bucket`, `storage_path`를 재사용하고 다음 필드를 추가한다.

| 필드 | 의미 |
|---|---|
| `storage_provider` | `SUPABASE` 또는 `NCLOUD` |
| `storage_bucket` | 비공개 버킷 이름 |
| `storage_path` | 영구 object key |
| `storage_url` | 서명 쿼리가 없는 canonical HTTPS URL |

기존 행은 `SUPABASE`, `storage_url=NULL`로 보존한다. 새 답변은 `NCLOUD`로 저장한다. Presigned URL은 DB에 저장하지 않는다. 운영 복구는 V8 적용 전 DB 백업을 기준으로 하며 자동 down migration은 제공하지 않는다.

## Ncloud와 환경변수

AWS SDK for Java v2의 재사용 가능한 `S3Client`·`S3Presigner`, custom endpoint, `kr-standard`, path-style, Signature V4를 사용한다. Public ACL은 설정하지 않는다.

```env
INTERVIEW_ANSWER_STORAGE_PROVIDER=NCLOUD
NCLOUD_OBJECT_STORAGE_ENDPOINT=https://kr.object.ncloudstorage.com
NCLOUD_OBJECT_STORAGE_REGION=kr-standard
NCLOUD_OBJECT_STORAGE_BUCKET=facefit-interview-videos
NCLOUD_ACCESS_KEY=replace-locally
NCLOUD_SECRET_KEY=replace-locally
NCLOUD_PRESIGNED_GET_TTL_SECONDS=300
```

실제 키는 `.env` 또는 배포 Secret에만 저장한다. `.env.example`, Git, 문서, 로그에 실제 값을 넣지 않는다. 버킷은 콘솔에서 Private으로 만들고 백엔드 계정에 필요한 PUT/GET/DELETE 권한만 부여한다.

## 업로드와 보상 처리

```text
POST /api/v1/interview-sessions/{sessionId}/answers
Content-Type: multipart/form-data
Idempotency-Key: ...
```

Spring은 1MB chunk로 임시 파일에 제한 복사하면서 SHA-256을 계산하므로 전체 영상을 `byte[]`로 만들지 않는다. MP4/WebM signature, MIME, 오디오·비디오 track, 200MB, 300초 검증을 유지한다.

```text
sessions/{sessionId}/turns/{turnId}/{answerId}.{mp4|webm}
```

사용자 파일명은 object key에 쓰지 않는다. Ncloud PUT에는 Content-Type, Content-Length, 정규화 확장자와 SHA-256 metadata를 설정한다. 업로드 또는 DB 확정 실패 시 같은 provider Adapter로 해당 객체를 삭제하고 기존 예약 답변·멱등성 복구 정책을 유지한다. 삭제 실패 로그에는 URL·인증정보를 넣지 않는다. 고아 객체는 버킷 전체가 아니라 `sessions/` 하위에서 DB 위치 정보와 대조해 별도 정리한다.

## canonical URL과 Presigned URL

canonical URL은 쿼리가 없는 영구 식별값이다.

```text
https://kr.object.ncloudstorage.com/{bucket}/sessions/.../{answerId}.webm
```

Worker는 STT/CV/VOICE attempt 직전에 `(provider, bucket, object key)`로 새 Presigned GET URL을 만든다. 재시도마다 새 URL을 만들며 기본 TTL은 300초다. URL은 DB·공개 API 응답·로그에 남기지 않는다. 기존 Supabase 답변은 `storage_provider=SUPABASE`로 라우팅하여 Supabase signed URL을 attempt 직전에 발급한다.

## Java-Python 내부 계약

STT/CV/VOICE의 URI와 응답·오류 계약은 유지하고 요청만 multipart binary에서 JSON URL로 변경한다.

```json
{
  "schemaVersion": "1",
  "requestId": "00000000-0000-4000-8000-000000000001",
  "answerId": "00000000-0000-4000-8000-000000000002",
  "mediaUrl": "https://kr.object.ncloudstorage.com/...?...signature...",
  "mediaMimeType": "video/webm",
  "mediaSizeBytes": 104857600,
  "recordedDurationSec": 180
}
```

저장 OpenAPI는 `ai-server/openapi/facefit-ai-openapi-v1.json`이다. 질문 생성과 CONTENT에는 media URL을 추가하지 않는다. CV 계산은 계속 Python이 담당하고 VOICE·CONTENT는 기존 `503 ANALYSIS_UNAVAILABLE`을 유지한다.

## Python 다운로드와 SSRF 방어

Python은 `httpx` streaming response를 request별 `0700` 임시 디렉터리에 기록한다.

- HTTPS 및 정확한 allowlist host만 허용
- userinfo, 비표준 포트, fragment, 4,096자 초과 URL 거절
- DNS 결과의 loopback/private/link-local/multicast/reserved/unspecified 주소 거절
- redirect 자동 추적 금지 및 3xx 거절
- connect/read timeout
- Content-Length 사전 제한과 실제 수신 200MB 제한
- 요청 MIME, 응답 Content-Type, MP4/WebM signature 검증
- 빈 응답, 크기 불일치, 부분 다운로드 거절
- 성공·오류·timeout 뒤 임시 파일과 디렉터리 삭제

```env
ANALYSIS_MEDIA_ALLOWED_HOST=kr.object.ncloudstorage.com
ANALYSIS_MEDIA_MAX_BYTES=209715200
ANALYSIS_MEDIA_CONNECT_TIMEOUT_SECONDS=5
ANALYSIS_MEDIA_READ_TIMEOUT_SECONDS=120
```

URL 쿼리, 원본 영상, 프레임, landmark는 로그로 출력하지 않으며 운영에서 `httpx` wire/debug logging을 켜지 않는다.

## 오류·Worker 정책

- 403/404, 손상·미지원 미디어, 크기·계약 위반: 영구 실패
- presign/일시 연결 실패, 다운로드 5xx/timeout: 기존 retryable 경로
- Python 503: 즉시 영구 실패
- Python 504/일시 네트워크 오류: 기존 최대 3회, 2초/10초 정책

atomic claim, worker token, `locked_at`, stale worker 방어, 완료 Job 방어, answer별 Job 유일성은 바꾸지 않는다.

## Docker와 테스트

```powershell
docker compose --env-file .env -f infra/compose/compose.dev.yml config --quiet
docker compose --env-file .env -f infra/compose/compose.dev.yml up --build -d
docker compose --env-file .env -f infra/compose/compose.dev.yml ps

cd backend
mvn -B -ntp test

cd ..
docker build --target test -f infra/docker/analysis-server.Dockerfile -t facefit-analysis-server:ncloud-test .
docker run --rm --entrypoint python facefit-analysis-server:ncloud-test -m unittest `
  tests.test_analysis_http_api tests.test_analysis_api_settings `
  tests.test_stt_http_analyzer tests.test_cv_analyzer tests.test_media_download -v
```

Python 컨테이너에는 Ncloud Access/Secret Key가 없어야 한다. 실제 Ncloud E2E는 인증정보가 있는 환경에서만 `test/` 전용 prefix의 작은 비인물 영상을 PUT, HEAD, presign GET, Python 검증, DELETE 순서로 수행한다. 버킷 전체나 다른 prefix를 삭제하면 안 된다.

## Lifecycle과 남은 정책

영상 보존기간은 확정되지 않았다. 운영 전 서비스 정책에 따라 예를 들어 1일/7일/30일 후보 중 하나를 결정하고 NCP 콘솔에서 Lifecycle을 설정해야 한다. 애플리케이션은 버킷 Lifecycle을 임의 변경하지 않는다. 세션·회원 삭제를 연결할 때는 DB 행을 먼저 지워 object key를 잃지 않도록 객체 삭제 결과를 확인한 뒤 기존 개인정보 삭제 정책을 적용한다.
