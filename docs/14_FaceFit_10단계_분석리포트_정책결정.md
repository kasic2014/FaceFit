# FaceFit 10단계 분석·리포트 정책 결정

## 범위

- `ANALYSIS-001`: `GET /api/v1/interview-sessions/{sessionId}/analysis-status`
- `REPORT-001`: `GET /api/v1/interview-sessions/{sessionId}/report`
- 답변 분석 의존성, 세션 분석 조정, 결정적 리포트 집계
- 실제 외부 AI·STT·CV·VOICE·CONTENT Adapter와 E2E 호출은 제외

## 상태 전이

```text
INTERVIEW_COMPLETED → ANALYZING → COMPLETED
```

- `completionType=NORMAL`인 세션만 분석한다.
- `INTERRUPTED` 세션은 분석·리포트 대상이 아니다.
- 확정 리포트 저장과 `COMPLETED` 전환은 같은 트랜잭션이다.
- 필수 분석 또는 리포트 생성이 최종 실패하면 `ANALYZING`을 유지한다.

## 작업 의존성과 소유권

```text
STT → CONTENT
CV ───────┐
VOICE ────┼→ REPORT_GENERATION
CONTENT ──┘
```

- CV와 VOICE는 STT와 병렬 실행할 수 있다.
- CONTENT는 같은 답변의 STT가 `SUCCEEDED`일 때만 Port를 호출한다.
- STT가 대기·처리·재시도 중이면 CONTENT는 claim하지 않는다.
- STT 최종 실패 시 CONTENT는 Port 호출 없이 `DEPENDENCY_FAILED`로 실패한다.
- 모든 Worker는 원자적 claim, UUID token, `lockedAt`, 최대 3회, 2초·10초 재시도와 stale claim 방어를 사용한다.
- 성공 작업은 다시 실행하거나 덮어쓰지 않는다.

## 정규화 결과

- STT 전사문은 답변 내부의 CONTENT 입력으로만 사용하며 API와 로그에 노출하지 않는다.
- CV 결과는 시선·자세 점수, VOICE 결과는 말하기 점수, CONTENT 결과는 내용 점수만 저장한다.
- 각 결과는 `schemaVersion`, 0~100 점수와 사용자 공개 가능 피드백만 저장한다.
- 외부 원본 응답, prompt, 디버그 값, Storage 위치와 원본 예외는 저장하지 않는다.

## 분석 상태

- 상태는 `WAITING`, `PROCESSING`, `SUCCEEDED`, `FAILED`다.
- 진행률은 `SUCCEEDED 작업 수 / 필수 작업 수 40 × 100`을 정수로 반올림한다.
- 실패 작업은 완료 진행률에 포함하지 않는다.
- 완료 답변 수는 네 작업이 모두 성공한 답변 수, 실패 답변 수는 하나 이상의 최종 실패 작업을 가진 답변 수다.
- 분석 실패 조회는 HTTP 200과 안전한 `ANSWER_ANALYSIS_FAILED`를 사용한다.

## 리포트 집계

- 필수 질문·답변 각 10개와 STT·CV·VOICE·CONTENT 각 10개 성공 시에만 `REPORT_GENERATION` 작업을 한 번 등록한다.
- GAZE는 CV 시선, POSTURE는 CV 자세, SPEECH는 VOICE 말하기, CONTENT는 CONTENT 내용 점수다.
- 축 점수는 10개 답변의 산술평균, 종합 점수는 네 축의 동일 가중치 평균이다.
- 모든 계산은 `RoundingMode.HALF_UP`으로 소수점 첫째 자리까지 확정 저장한다.
- 강점은 점수 내림차순 상위 2축, 개선은 오름차순 하위 2축이다.
- 동점 순서는 `GAZE`, `POSTURE`, `SPEECH`, `CONTENT`로 고정한다.
- 부분 리포트와 누락 점수의 0점 대체는 허용하지 않는다.

## 조회와 보안

- 본인 소유, ACTIVE, 온보딩 완료 세션만 조회한다.
- 타인과 존재하지 않는 세션은 모두 404다.
- 리포트 대기·생성 중은 202, 완료는 200, 분석 실패 차단은 409, 리포트 최종 실패는 503이다.
- 응답에는 전사문, 원문, Storage 정보, Worker token, 내부 URL과 원본 오류를 포함하지 않는다.
- 조회 API는 작업이나 리포트를 생성하지 않는다.

## 실행 정책

- 실제 외부 Adapter가 없으므로 자동 dispatch와 stale recovery는 기본 비활성화다.
- 테스트에서는 명시적으로 Worker와 조정 서비스를 실행한다.
