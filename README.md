# Face-Fit

Face-Fit은 사용자의 발화, 시선, 자세를 분석하고 맞춤형 음성을 생성해 면접 연습을 돕는 AI 면접 코칭 서비스입니다.

## 담당 AI 기능

- faster-whisper 기반 발화 분석
- MediaPipe 기반 시선 분석
- MediaPipe 기반 자세 분석
- Qwen3-TTS 기반 음성 생성 및 음성 클론

## 기본 폴더 구조

```text
face-fit/
├── backend/
├── frontend/
├── ai-server/
│   ├── analysis-server/
│   │   ├── app/
│   │   │   ├── speech/
│   │   │   ├── vision/
│   │   │   ├── schemas/
│   │   │   └── core/
│   │   ├── data/
│   │   │   ├── input/
│   │   │   │   ├── audio/
│   │   │   │   └── video/
│   │   │   ├── output/
│   │   │   └── temp/
│   │   ├── scripts/
│   │   ├── tests/
│   │   ├── logs/
│   │   └── .venv/
│   └── tts-server/
│       ├── app/
│       ├── data/
│       │   ├── reference_voice/
│       │   ├── output/
│       │   └── temp/
│       ├── scripts/
│       ├── tests/
│       └── logs/
├── .vscode/
├── .gitignore
└── README.md
```

## AI 서버 분리 이유

`analysis-server`는 faster-whisper와 MediaPipe를 이용한 분석 작업을 담당하고, `tts-server`는 Qwen3-TTS를 이용한 음성 생성과 음성 클론을 담당합니다. 두 서버를 분리하면 서로 다른 의존성과 실행 자원을 독립적으로 관리할 수 있고, 기능별 배포와 확장이 쉬워집니다.

## Python 버전 및 현재 상태

- 사용할 Python 버전: Python 3.12
- 현재 단계에서는 AI 라이브러리를 설치하지 않았습니다.
- 다음 단계는 `analysis-server` 개발환경 점검 및 최소 테스트 코드 작성입니다.
