# Face-Fit (AI 기반 모의면접 플랫폼)

Face-Fit은 사용자 면접 연습, 음성·운율 분석, 시선·자세 분석 및 AI 면접관 TTS 서비스를 제공하는 멀티 서비스 플랫폼입니다.

## 담당 AI 기능

- faster-whisper 기반 발화 분석
- MediaPipe 기반 시선 분석
- MediaPipe 기반 자세 분석
- Qwen3-TTS 기반 음성 생성 및 음성 클론

---

## 기본 폴더 구조

```text
face-fit/
├── backend/                  # 백엔드 서버 (Java 21 / Spring Boot 3.5)
├── frontend/                 # 프론트엔드 프로젝트 (React / Vite)
├── ai-server/                # AI 엔진 서버
│   ├── analysis-server/      # 발화/시선/자세 분석 서버
│   └── tts-server/           # Qwen3-TTS 기반 음성 생성 및 클론 서버
├── docs/                     # 시스템 아키텍처 및 API/AI 명세서
├── infra/                    # Docker, Nginx 및 멀티 컨테이너 배포 설정
├── scripts/                  # 로컬 실행 및 통합 검증 스크립트
├── .vscode/                  # vscode 설정
├── .gitignore                # 깃 관리 제외 설정
└── README.md                 # 프로젝트 통합 가이드
```

## AI 서버 분리 이유

`analysis-server`는 faster-whisper와 MediaPipe를 이용한 분석 작업을 담당하고, `tts-server`는 Qwen3-TTS를 이용한 음성 생성과 음성 클론을 담당합니다. 두 서버를 분리하면 서로 다른 의존성과 실행 자원을 독립적으로 관리할 수 있고, 기능별 배포와 확장이 쉬워집니다.

---

## 시작하기 및 실행 방법

### 1. 로컬 환경 통합 실행 및 검증 (Scripts)

루트에 포함된 스크립트를 통해 전체 서비스 설정을 쉽고 간편하게 구성하고 검증할 수 있습니다.

```bash
# 로컬 개발 환경 준비 (의존성 및 설정 파일 셋업)
./scripts/setup.ps1

# 전체 테스트 실행
./scripts/test-all.ps1

# 로컬 개발 서버 동시 실행 (프론트엔드 + 백엔드 + AI 서버)
./scripts/run-local.ps1
```

### 2. 프론트엔드 (Frontend)

Vite + React + TypeScript 환경의 프론트엔드 프로토타입입니다.

* **요구 사양**: Node.js 24 이상
* **개발 서버 실행 방법**:
  ```bash
  cd frontend
  npm ci
  npm run dev
  ```
  실행 후 브라우저에서 `http://localhost:3000`으로 접속 가능합니다.

* **정적 검사 및 빌드**:
  ```bash
  npm run lint
  npm run typecheck
  npm run build
  ```

### 3. 백엔드 (Backend)

Java 21 및 Spring Boot 3.5 기반으로 작성된 API 서버입니다.

* **요구 사양**: Java 21 이상, Maven
* **로컬 실행 방법**:
  ```bash
  cd backend
  ./mvnw spring-boot:run
  ```

### 4. AI 서버 (AI Server)

* **요구 사양**: Python 3.12
* 현재 단계에서는 기본적인 패키지 구조와 분석 스크립트 뼈대만 잡혀 있는 상태이며, 개발 환경 검증을 위한 테스트 코드들이 포함되어 있습니다.

---

## Docker를 통한 로컬 실행 (프론트엔드 & 전체 인프라)

`docker compose up` 또는 infra 내 설정을 통해 로컬에서 컨테이너 기반으로 서비스를 실행할 수 있습니다.
```bash
# 프론트엔드 로컬 컴포즈 가동
docker compose up
```
Vite 번들이 빌드되며, Nginx가 내장된 컨테이너가 포트 `3000`에서 가동됩니다. SPA 라우팅 폴백 설정이 처리되어 `/session/live` 등의 경로에 직접 접속해도 정상 동작합니다.

---

## CI/CD 자동화 및 테스트 검증

- **GitHub Actions 연동**: `main` 및 `develop` 브랜치 푸시 시 AI Analysis Server 검증 테스트(`ai-analysis-test.yml`), Docker Compose 설정 검증 및 자동 배포가 수행됩니다.
- **AI Analysis Server 테스트**: Faster-Whisper STT 분석, MediaPipe 시선·자세 분석 및 HTTP 비동기 세션 계약 자동 단위 테스트 수록.

<!-- test trigger: 2026-08-04 (CI test & branch sync completed) -->
