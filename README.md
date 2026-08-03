# Face-Fit (AI 기반 모의면접 플랫폼)

Face-Fit은 사용자 면접 연습, 음성·운율 분석, 시선·자세 분석 및 AI 면접관 TTS 서비스를 제공하는 멀티 서비스 플랫폼입니다.

## 모듈 구성

- `frontend/`: 사용자 면접 연습 Web 화면
- `backend/`: 회원, 면접 세션, 문서 및 결과 관리 API (Java 21 / Spring Boot 3.5)
- `ai-server/`:
  - `analysis-server/`: 발화, STT, 운율 분석 서버
  - `vision-server/`: 시선, 자세, 영상 분석 서버
  - `tts-server/`: AI 면접관 음성 합성 서버
- `docs/`: 시스템 아키텍처 및 API/AI 명세서
- `infra/`: Docker, Nginx 및 멀티 컨테이너 배포 설정
- `scripts/`: 로컬 실행 및 통합 검증 스크립트

## 시작하기

```bash
# 로컬 개발 환경 준비
./scripts/setup.ps1

# 전체 테스트 실행
./scripts/test-all.ps1

# 로컬 개발 서버 동시 실행
./scripts/run-local.ps1
```
