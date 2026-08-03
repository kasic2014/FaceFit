# Face-Fit

Face-Fit은 사용자의 발화, 시선, 자세를 분석하고 맞춤형 음성을 생성해 면접 연습을 돕는 AI 면접 코칭 서비스입니다.

## 담당 AI 기능

- faster-whisper 기반 발화 분석
- MediaPipe 기반 시선 분석
- MediaPipe 기반 자세 분석
- Qwen3-TTS 기반 음성 생성 및 음성 클론

---

## 기본 폴더 구조

```text
face-fit/
├── backend/                  # 백엔드 서버 (Django / FastAPI 등)
├── frontend/                 # 프론트엔드 프로젝트 (React / Vite)
├── ai-server/                # AI 엔진 서버
│   ├── analysis-server/      # 발화/시선/자세 분석 서버
│   └── tts-server/           # Qwen3-TTS 기반 음성 생성 및 클론 서버
├── .vscode/                  # vscode 설정
├── .gitignore                # 깃 관리 제외 설정
└── README.md                 # 프로젝트 통합 가이드
```

## AI 서버 분리 이유

`analysis-server`는 faster-whisper와 MediaPipe를 이용한 분석 작업을 담당하고, `tts-server`는 Qwen3-TTS를 이용한 음성 생성과 음성 클론을 담당합니다. 두 서버를 분리하면 서로 다른 의존성과 실행 자원을 독립적으로 관리할 수 있고, 기능별 배포와 확장이 쉬워집니다.

---

## 하위 프로젝트 설정 및 실행 방법

### 1. 프론트엔드 (Frontend)

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

### 2. AI 서버 (AI Server)

* **요구 사양**: Python 3.12
* 현재 단계에서는 기본적인 패키지 구조와 분석 스크립트 뼈대만 잡혀 있는 상태이며, 개발 환경 검증을 위한 테스트 코드들이 포함되어 있습니다.

---

## Docker를 통한 로컬 실행 (프론트엔드)

`docker compose up`을 통해 로컬에서 컨테이너 기반으로 프론트엔드를 실행할 수 있습니다.
```bash
docker compose up
```
Vite 번들이 빌드되며, Nginx가 내장된 컨테이너가 포트 `3000`에서 가동됩니다. SPA 라우팅 폴백 설정이 처리되어 `/session/live` 등의 경로에 직접 접속해도 정상 동작합니다.
