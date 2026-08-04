# FACE-FIT 14단계 Docker Compose 실행 가이드

## 구성

14단계 Compose 구성은 다음 두 서비스만 실행한다.

| 서비스 | Compose 이름 | 컨테이너 포트 | Health endpoint |
|---|---|---:|---|
| Spring Boot 백엔드 | `backend` | 8080 | `/actuator/health` |
| Python AI 서버 | `analysis-server` | 8001 | `/health` |

Supabase Auth·PostgreSQL·Private Storage는 외부 Supabase를 그대로 사용한다. 로컬 PostgreSQL 컨테이너는 생성하지 않는다. 백엔드는 Compose 네트워크에서 `http://analysis-server:8001`로 AI 서버를 호출한다. 컨테이너의 `localhost`는 같은 컨테이너 자신을 뜻하므로 서비스 간 주소로 사용하면 안 된다.

## 준비와 실행

저장소 루트에서 예제 파일을 복사한 뒤 실제 개발 환경 값을 로컬 `.env`에 입력한다.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env -f infra/compose/compose.dev.yml config
docker compose --env-file .env -f infra/compose/compose.dev.yml build
docker compose --env-file .env -f infra/compose/compose.dev.yml up -d
docker compose --env-file .env -f infra/compose/compose.dev.yml ps
```

실제 `.env`는 Git에서 제외된다. `.env.example`의 `replace-with-...` 값은 설명용이며 실제 인증정보가 아니다.

## 필수 환경변수

백엔드까지 정상 기동하려면 다음 값을 실제 외부 Supabase 환경에 맞춰야 한다.

| 변수 | 용도 |
|---|---|
| `DB_URL` | Supabase PostgreSQL JDBC URL |
| `DB_USERNAME` | DB 사용자 |
| `DB_PASSWORD` | DB 비밀번호 |
| `SUPABASE_JWT_ISSUER_URI` | Supabase Auth JWT issuer |
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_SECRET_KEY` | Private Storage 접근용 secret/service-role key |
| `FACEFIT_AI_SERVICE_TOKEN` | 백엔드와 AI 서버가 함께 사용하는 내부 Bearer token |

Bucket 이름은 `CAREER_DOCUMENTS_BUCKET`, `JOB_POSTINGS_BUCKET`, `INTERVIEW_ANSWERS_BUCKET`으로 변경할 수 있다. 포트는 `BACKEND_PORT`, `AI_SERVER_PORT`로 변경한다.

Compose는 백엔드 컨테이너의 `FACEFIT_AI_BASE_URL`을 `http://analysis-server:8001`로 직접 설정한다. 호스트에서 Spring Boot를 단독 실행할 때만 다음처럼 호스트 포트를 사용한다.

```powershell
$env:FACEFIT_AI_BASE_URL = 'http://localhost:8001'
```

## 로컬 실행과 Docker 실행의 차이

| 항목 | 로컬 프로세스 | Docker Compose |
|---|---|---|
| AI 기본 URL | `http://localhost:8001` | `http://analysis-server:8001` |
| 환경변수 | IDE·PowerShell·Secret 관리 도구에서 주입 | 저장소 루트의 로컬 `.env`에서 Compose가 주입 |
| Python 바인딩 | 명시적으로 `0.0.0.0:8001` | 이미지 명령에 고정 |
| 실행 사용자 | 로컬 사용자 | 두 이미지 모두 `facefit` non-root 사용자 |
| Supabase | 외부 서비스 | 외부 서비스, 동일 |

## Healthcheck와 내부 통신 확인

```powershell
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8080/actuator/health
docker compose --env-file .env -f infra/compose/compose.dev.yml ps
docker compose --env-file .env -f infra/compose/compose.dev.yml exec backend `
  wget -q -O - http://analysis-server:8001/health
```

AI 서버가 `healthy`가 된 뒤 백엔드를 시작하도록 `depends_on: condition: service_healthy`가 설정되어 있다.

## 테스트

Java 전체 테스트:

```powershell
Set-Location backend
.\mvnw.cmd -B -ntp test
```

Python 내부 HTTP 계약 테스트:

```powershell
Set-Location ai-server/analysis-server
python -m pip install -r requirements-cpu.txt
python -m unittest `
  tests.test_analysis_http_api `
  tests.test_analysis_api_settings `
  tests.test_stt_http_analyzer -v
```

`requirements-cpu.txt`는 기존 `requirements.txt`를 포함하면서 Compose·CI에 맞는 공식 PyTorch CPU wheel만 고정한다. CUDA runtime을 이미지에 불필요하게 포함하지 않는다.

Compose와 이미지 검증:

```powershell
docker compose --env-file .env.example `
  -f infra/compose/compose.dev.yml config --quiet
docker compose --env-file .env.example `
  -f infra/compose/compose.dev.yml build backend analysis-server
```

CV·VOICE·CONTENT는 운영 분석 구현 전이므로 유효한 내부 인증과 요청을 보내도 계약대로 `503 ANALYSIS_UNAVAILABLE`을 반환한다. 가짜 성공이나 0점 대체를 사용하지 않는다.

## 문제 해결

- 백엔드 컨테이너에서 AI 연결이 거부되면 `FACEFIT_AI_BASE_URL`이 `localhost`가 아닌 `http://analysis-server:8001`인지 Compose 최종 설정에서 확인한다.
- 호스트 포트 충돌이면 `.env`의 `BACKEND_PORT` 또는 `AI_SERVER_PORT`만 바꾼다. 컨테이너 내부 포트 8080·8001은 바꾸지 않는다.
- 백엔드 health가 실패하면 `DB_URL`, DB 계정, JWT issuer를 먼저 확인한다. 외부 Supabase DB가 없으면 JPA/Flyway 단계에서 안전하게 기동 실패한다.
- 분석 API가 401이면 두 컨테이너의 `FACEFIT_AI_SERVICE_TOKEN`이 동일하지 않은 것이다. 빈 token이면 분석 API는 안전하게 503으로 닫힌다.
- AI 모델이 CPU 환경에서 실행되지 않으면 `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`을 확인한다.
- 민감정보를 확인할 때 `docker compose config` 전체 출력이나 컨테이너 환경변수를 CI 로그에 남기지 않는다. 검증에는 `config --quiet`을 사용한다.

## 종료와 정리

```powershell
docker compose --env-file .env -f infra/compose/compose.dev.yml down --remove-orphans
```

이 구성은 별도 데이터 volume을 만들지 않으므로 종료 시 두 컨테이너와 전용 네트워크만 정리된다.

## 비밀정보 관리

- 실제 `.env`, JWT, DB 비밀번호, Supabase secret/service-role key를 커밋하지 않는다.
- 값이 없는 예제 파일만 `.env.example`로 관리한다.
- GitHub Actions에서 실제 Supabase E2E가 필요해질 때는 GitHub Environments/Actions Secrets로 주입하고 로그에 출력하지 않는다.
- 커밋 전 `git status --short`와 `git grep`으로 실수로 추가된 `.env` 및 secret 패턴을 확인한다.
