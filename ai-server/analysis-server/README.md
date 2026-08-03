# Analysis Server

발화(Speech), STT(Whisper), 운율(Prosody) 분석 서버입니다.

## 기능

- Whisper 서비스 기반 STT 텍스트 변환
- 발화 속도(WPM), 침묵 구간, 발화 휴지 분석
- 운율(Prosody) 특징 추출 및 검증 데이터셋 처리
- Spring Boot 내부 연동용 AI HTTP 계약

## 내부 HTTP 계약

```text
GET  /health
POST /internal/v1/analyses/stt
POST /internal/v1/analyses/cv
POST /internal/v1/analyses/voice
POST /internal/v1/analyses/content
```

분석 endpoint는 `Authorization: Bearer {AI_SERVICE_TOKEN}`과 UUID 형식의
`X-Request-Id`가 필요하다. `/health`는 기존 배포 점검 호환성을 위해 인증 없이
유지한다.

- STT: 기존 `WhisperService`를 사용하는 실제 성공 경로가 구현되어 있다.
- CV: 운영 GAZE·POSTURE 점수 산식이 없어 `503 ANALYSIS_UNAVAILABLE`이다.
- VOICE: 운영 SPEECH 점수 산식이 없어 `503 ANALYSIS_UNAVAILABLE`이다.
- CONTENT: 모델·Prompt·평가 기준이 없어 `503 ANALYSIS_UNAVAILABLE`이다.

CV·VOICE·CONTENT의 503은 임시 성공 응답이나 0점 대체가 아니다.

OpenAPI 기준 파일:

```text
../openapi/facefit-ai-openapi-v1.json
```

## 환경 설정

```bash
cp .env.example .env
pip install -r requirements.txt
```

`FACEFIT_AI_SERVICE_TOKEN`에는 배포 환경의 Secret을 주입한다. 실제 값을
`.env.example`, 로그 또는 Git에 기록하지 않는다.

기본 미디어 계약은 영상과 음성 스트림을 모두 가진 MP4·WebM, 최대 200MB·300초다.
업로드는 제한된 청크로 임시 파일에 저장하며 확장자가 아닌 Content-Type과 파일
시그니처를 함께 검사한다. STT 실행 전 PyAV로 영상·음성 스트림과 실제 재생
시간을 검증한다.

모델 timeout 기본값은 55초이며 HTTP 계층의 자동 재시도는 없다. 재시도는
Spring Worker 정책에서만 수행한다.

## 실행

```powershell
$env:FACEFIT_AI_SERVICE_TOKEN = '<secret-from-secret-manager>'
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## OpenAPI 생성

```powershell
python scripts/export_openapi.py
```

동일 소스에서 반복 생성한 JSON의 SHA-256은 같아야 한다.

## HTTP 계약 테스트

```powershell
python -m unittest `
  tests.test_analysis_http_api `
  tests.test_analysis_api_settings `
  tests.test_stt_http_analyzer -v
```

실제 Whisper 모델 E2E는 모델·GPU·테스트 미디어가 준비된 명시적 환경에서 별도로
실행한다. 계약 테스트의 주입형 분석기는 테스트에만 존재하며 운영 `app`에는
등록되지 않는다.
