# Face-Fit AI Server

Face-Fit 모의면접 AI 멀티 서버 아키텍처입니다.

## 서버 역할 및 구조

1. **`analysis-server/`**: 발화(Speech), STT(Whisper), 운율(Prosody) 분석 서버
   - 음성 데이터 처리, 텍스트 변환 및 발화 속도·억양 분석
2. **`vision-server/`**: 시선(Gaze), 자세(Posture), 영상 분석 서버
   - 시선 추적, 두부 자세, 어깨 밸런스 및 구간 통합 특징 산출
3. **`tts-server/`**: AI 면접관 음성 합성 서버
   - 면접관 질문 음성 생성 (Qwen3-TTS 연동 예정)

## 서버 간 통신 방식

- 백엔드 서버(Spring Boot)에서 REST API 또는 비동기 메시지 큐를 통해 AI 분석 작업을 요청합니다.
- 분석 결과는 규격화된 JSON 스키마 형태로 백엔드 서버로 응답합니다.
