# Face-Fit AI MVP development completion report

## 1. 범위

AI 담당 범위는 단일 실제 면접 Session을 대상으로 한 Vision 측정, 오디오 표준화, 한국어 STT, 발화 특성 측정, 두 FastAPI, 비동기 Analysis Job 실행, Docker 환경, Vision·Analysis 통합 계약 및 Backend Handoff 패키지다. Backend Java, Frontend, DB, LLM, RAG, TTS는 범위 밖이다.

## 2. 기술 Stack

- Python 3.12
- FastAPI, Pydantic, Uvicorn
- MediaPipe 기반 Vision 측정
- FFmpeg 기반 오디오 추출·표준화
- Faster-Whisper 1.2.1, CTranslate2 4.8.1
- NumPy 기반 speech measurement
- Docker Compose
- 표준 `unittest`, Strict JSON, atomic file replace

## 3. 구현 Stage

- Vision 단일 Session 입력·측정·피드백 및 API
- Stage 24: STT 입력 오디오 추출·표준화·답변 구간 분리
- Stage 25: Faster-Whisper 한국어 Session 전사
- Stage 26: 발화 속도·침묵·간투어·음량·피치 측정
- Stage 27: STT·Speech Analysis FastAPI
- Stage 27.1: 비동기 queue·동시성·lock·보존 정책
- Stage 27.2: Analysis Docker 실행 환경
- Stage 28: Vision·Analysis 통합 Session 계약 및 E2E
- Stage 29: Backend Handoff Schema·Example·가이드·최종 검증

## 4. Vision

SES_000001 Answer 4개에서 얼굴과 양쪽 어깨 측정이 가능했다. Head Pose는 일부 프레임에서만 가용하며 누락값을 임의 보간하지 않는다. 결과는 채용 점수나 심리 추론이 아니다.

## 5. Audio preprocessing

원본 매체에서 STT 입력 오디오를 추출하고 표준 형식으로 변환한 뒤 공식 Answer interval에 따라 네 구간으로 분리한다. 실제 WAV, 원본 영상 및 내부 경로는 Git과 API 계약에서 제외된다.

## 6. Faster-Whisper STT

한국어 `large-v3-turbo` 고정 revision을 local-only로 사용했다. SES_000001 결과는 STT Answer 4, Segment 27, Word 307이다. Segment 경계 경고를 보존한다.

## 7. Speech characteristics

발화 속도, word timestamp pause, acoustic silence, filler candidate, volume, physical F0 pitch를 측정한다. Filler Candidate는 1개이며 사람 검토가 필요하고, Pitch는 네 Answer에서 사용 가능하다. 평가 threshold는 승인되지 않았다.

## 8. Vision API

Vision Job 생성·조회와 Session feedback 조회를 제공한다. 상태는 `QUEUED`, `RUNNING`, `SUCCEEDED`, `SUCCEEDED_WITH_LIMITATIONS`, `FAILED`다. 파일 경로나 Participant 입력을 받지 않는다.

## 9. Analysis API

Analysis Job 생성·조회, transcription, speech-characteristics 결과 조회를 제공한다. POST는 Job을 queue에 저장하고 즉시 반환하며 worker가 처리한다. Production transcript text는 기본 비노출이다.

## 10. 비동기 Queue와 Lock

worker 수와 queue capacity가 제한된다. 같은 Session·pipeline의 STT GPU 실행은 process 내부에서도 직렬화된다. execution lock은 exclusive create와 atomic JSON을 사용하며 성공·실패 후 해제된다. restart와 shutdown은 미완료 Job을 보수적으로 실패 처리한다.

## 11. Docker

Vision과 Analysis container health가 검증됐다. Analysis image는 비root 사용자로 실행하고 모델·실제 데이터·환경파일을 image에 포함하지 않는다. 모델 캐시는 read-only다.

## 12. Vision·Analysis Integration

두 서버는 서로 직접 호출하거나 내부 모듈을 import하지 않는다. 독립 Job polling 후 공개 결과를 Session·Answer·timestamp 계약으로 결합한다. 반복 실행에서 동일 Job 재사용과 안정 필드 일치를 확인했다.

## 13. 테스트 현황

- Analysis unittest: 830개 통과
- Analysis runtime: 6개 통과
- Vision unittest: 723개 통과
- Integration unittest: 42개 통과
- Stage 29 Handoff unittest: 38개 통과
- Stage 29 Validator: 필수 파일·Schema·Example·OpenAPI compatibility 통과
- Analysis와 Vision `pip check`: 통과
- 제품 검증 PermissionError: 0건

## 14. 보안과 개인정보

실제 media, WAV, transcript 원문, speech 원본 결과, Vision 원본 결과, Participant, consent, metadata, annotation, rater 및 내부 경로를 Handoff package에 포함하지 않는다. 모든 예제는 합성·비식별 값이고 transcript text는 null이다. Strict JSON은 NaN과 Infinity를 금지한다.

## 15. 현재 제한

- 단일 실제 Session 기반 MVP
- Head Pose 일부 프레임만 가용
- 승인된 scoring threshold 없음
- Agreement·Kappa 운영 적용 전
- Filler Candidate 사람 검토 필요
- GPU Docker 실제 forceRebuild 전사 미검증
- 다중 사용자 분석 미검증
- 감정·성격·합격 가능성 추론 미제공

이 제한은 현재 측정 결과와 Handoff 계약을 실패로 만들지 않지만 운영 정책에서 명시해야 한다.

## 16. Backend 전달 사항

Backend는 두 Job ID와 request ID를 저장하고 독립 polling한다. 원본 source status를 보존하며 Warning을 오류로 바꾸지 않는다. timestamp 단위는 millisecond이고 구간은 `[start, end)`다. `forceRebuild=false`를 기본으로 사용하고 점수·등급을 생성하지 않는다.

## 17. 향후 개선 과제

1. GPU Docker runtime dependency 해결과 실제 강제 재전사 검증
2. 추가 실제 Session 수집
3. Annotation agreement·adjudication 운영
4. 승인 evidence 기반 threshold·scoring 연구
5. CI/CD
6. 운영 monitoring·logging·metrics

모두 현재 AI MVP 완료와 분리된 선택 작업이다.

## 18. 최종 완료 상태

실제 API 계약, JSON Schema, 비식별 Example, polling·오류·Docker guide와 최종 E2E 계약이 준비됐다. Head Pose, STT, filler 및 GPU 제한이 남아 있으므로 최종 상태는 `ai_backend_handoff_ready_with_warnings`다. Face-Fit AI 담당 면접 MVP 필수 개발 범위는 완료됐다.
