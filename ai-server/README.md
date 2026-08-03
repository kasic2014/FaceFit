# Face-Fit AI Server

Face-Fit 모의면접 AI 멀티 서버 아키텍처입니다.

## 서버 역할 및 구조

1. **`analysis-server/`**: 발화(Speech), STT(Whisper), 운율(Prosody) 분석 서버
   - 음성 데이터 처리, 텍스트 변환 및 발화 속도·억양 분석
2. **`vision-server/`**: 시선(Gaze), 자세(Posture), 영상 분석 서버
   - 시선 추적, 두부 자세, 어깨 밸런스 및 구간 통합 특징 산출
3. **`tts-server/`**: AI 면접관 음성 합성 서버
   - 면접관 질문 음성 생성 (Qwen3-TTS 연동 예정)

루트 `ai-server/`가 운영 변경의 단일 기준이다. `FaceFit/ai-server/`는 이전
사본으로 취급하며 자동 동기화하거나 삭제하지 않는다.

## 서버 간 통신 방식

- 내부 HTTP 계약의 단일 진입점은 현재 `analysis-server`다.
- Spring Boot는 Bearer 서비스 토큰과 UUID `X-Request-Id`로 요청한다.
- STT는 실제 Whisper 서비스 경계를 사용한다.
- CV·VOICE·CONTENT는 HTTP 계약은 존재하지만 운영 분석 산식이나 모델이 없어
  `503 ANALYSIS_UNAVAILABLE`을 반환한다.
- 기준 OpenAPI는 `openapi/facefit-ai-openapi-v1.json`이다.
