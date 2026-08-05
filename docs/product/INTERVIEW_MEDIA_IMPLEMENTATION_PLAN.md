# 면접 미디어·MuseTalk 구현 계획

| 항목 | 내용 |
| --- | --- |
| 목적 | 현재 목업을 실제 장치·답변 업로드·MuseTalk 질문 영상·분석 API와 연결한다. |
| 기준 | [API v0.3.6](FaceFit_백엔드_API_명세서_v0.3.md), [MuseTalk 아키텍처](REALTIME_AVATAR_ARCHITECTURE.md) |
| 대상 | 프론트엔드, 백엔드, AI, QA |
| 상태 | 구현 계획·실장치 검증 대기 |

## 현재 구현과 공백

- 카메라·마이크 접근 hook과 프리뷰는 부분 구현됐다.
- 라이브 화면은 고정 5문항과 700ms 저장 타이머를 사용한다.
- `MediaRecorder`, 답변 Blob, 실제 세션·질문 ID, 업로드 재시도는 미연동이다.
- 캐릭터는 프론트 반응형 UI와 MuseTalk 질문 MP4로 분리해야 한다.

## 단계별 계획

| 단계 | 결과 | 완료 조건 |
| --- | --- | --- |
| 1. 장치 기반 | 실제 카메라·마이크·장치 변경 | 권한 거부·없음·분리·재연결 검증 |
| 2. 답변 녹화 | 질문별 MP4/WebM Blob | 답변당 Blob 1개, 중복 완료 0건 |
| 3. API 연결 | 세션·질문·답변 polling/upload | 멱등성·오프라인·timeout 복구 |
| 4. MuseTalk 출력 | 질문별 MP4 재생·정적 폴백 | READY·PROCESSING·FAILED_FALLBACK 검증 |
| 5. 분석·리포트 | 실제 분석 상태·결과 이동 | 정상·부분·전체 실패 처리 |
| 6. QA·인계 | 브라우저·장치·AI 테스트셋 | P0 QA와 데이터 삭제 검증 |

## 프론트 구현 계약

- 라우트는 `/sessions/:sessionId/live`를 사용한다.
- 질문 배열과 고정 `5` 카운터를 제거하고 `questionId`, `questionKind`,
  `baseQuestionOrder`, `nextQuestionStatus`를 사용한다.
- `characterMediaStatus=READY`이면 `QUESTION-002`로 `PlaybackAccess`를 발급받아 `MEDIA-003` MP4를 재생한다. `<video>`에 Bearer 헤더를 붙이지 않는다.
- `QUEUED|PROCESSING`에서는 정적 캐릭터 로딩 반응을 표시한다.
- `FAILED_FALLBACK`에서는 정적 캐릭터+질문 텍스트로 답변을 진행한다.
- 영상 재생 종료 후 답변 녹화를 시작한다. 영상 중단은 클라이언트 동작이며 API를 호출하지 않는다.

## 답변 녹화·업로드

- `MediaRecorder.isTypeSupported`로 MIME을 선택한다.
- 질문 시작·종료 UTC, duration, codec, width, height, FPS, `endedBy`를 기록한다.
- 발화 3초 후 VAD를 켜고 2초 무음이면 1초 카운트다운을 표시한다. 재발화는 취소, 버튼·Space·VAD 확정은 하나의 완료 명령으로 합쳐 중복 Blob을 막는다.
- `ANSWER-001`에 동일 `Idempotency-Key`로 재전송한다.
- 미전송 Blob은 IndexedDB에 임시 보관하고 이탈 경고를 표시한다.

## QA 추적

| ID | 시나리오 | 기대 결과 |
| --- | --- | --- |
| MED-01 | 권한 허용·거부·장치 없음 | 실제 상태와 복구 행동 표시 |
| REC-01 | 버튼·Space 연속 입력 | 답변·업로드 1건 |
| UP-01 | timeout·오프라인 | 중복 없이 재전송 |
| CHAR-01 | MuseTalk READY | MP4 재생 후 녹화 시작 |
| CHAR-02 | 20초 timeout·생성 실패 | 정적 캐릭터로 면접 지속 |
| CHAR-03 | 다시 듣기 | 기존 MP4 재생, GPU 작업 없음 |
| AN-01 | 분석 정상·부분·실패 | 상태와 다음 행동 일치 |

## 완료 조건

- 샘플 데이터·고정 타이머 없이 한 세션이 정상 종료된다.
- 기본 5문항과 생성된 꼬리질문이 실제 ID로 기록된다.
- 미디어·MuseTalk 장애가 답변 손실이나 무한 로딩을 만들지 않는다.
- Chrome·Edge 실장치 결과와 AI 인계 manifest가 남는다.
