# Environment and Docker guide

## Host 환경변수

Integration:

- `FACEFIT_VISION_API_BASE_URL=http://127.0.0.1:8000`
- `FACEFIT_ANALYSIS_API_BASE_URL=http://127.0.0.1:8002`
- `FACEFIT_INTEGRATION_POLL_INTERVAL_MS=250`
- `FACEFIT_INTEGRATION_TIMEOUT_SECONDS=120`
- `FACEFIT_INTEGRATION_EXPOSE_TRANSCRIPT_TEXT=false`

Production Analysis는 `ANALYSIS_API_EXPOSE_TRANSCRIPT_TEXT=false`를 사용한다. 실제 `.env`, 모델 캐시 경로 및 credential은 Handoff 패키지에 포함하지 않는다.

## Compose 실행

Repository root에서 실행한다.

```powershell
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml ps
docker compose -f docker-compose.local.yml logs --no-color
```

Health:

- Vision: `http://127.0.0.1:8000/health`
- Analysis: `http://127.0.0.1:8002/health`

Docker 내부 호출:

- Vision: `http://vision-server:8000`
- Analysis: `http://analysis-server:8002`

통합 스모크:

```powershell
python ai-server/integration/scripts/smoke_integrated_ai_services.py `
  --session-id SES_000001 `
  --vision-base-url http://127.0.0.1:8000 `
  --analysis-base-url http://127.0.0.1:8002
```

종료:

```powershell
docker compose -f docker-compose.local.yml down
```

종료 후 Analysis port 8002, 임시 network, Analysis container, lock 파일이 남지 않았는지 확인한다.

## 모델 정책

Analysis image는 모델을 포함하지 않는다. 모델 캐시는 read-only bind mount이며 host 경로를 API나 보고서에 기록하지 않는다. 기존 결과 조회 E2E는 `forceRebuild=false`로 수행한다.

검증 완료 범위:

- Analysis Docker CPU runtime 및 기존 결과 조회
- NVIDIA 장치 감지
- CTranslate2 CUDA capability 확인
- 고정 revision 모델 local-only load

미검증 범위:

- Docker GPU 실제 `forceRebuild=true` 전사

따라서 GPU limitation을 제거하거나 GPU 문제가 해결됐다고 표시하면 안 된다.

## 기존 운영 컨테이너 보호

검증 전에 이미 Vision container가 실행 중이면 image ID, restart policy, port, network를 기록한다. 검증용 Compose 종료 후 기존 container를 원래 이름과 상태로 복원한다. 다른 Compose project의 container를 임의 삭제하거나 재생성하지 않는다.
