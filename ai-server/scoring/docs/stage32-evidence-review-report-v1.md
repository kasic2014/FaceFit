# Stage 32 Gap Evidence 원문 검토 보고서 v1

## 결론

Stage 32에서 확보된 정확히 18개 자료를 파일 무결성, 원문 위치, Face-Fit metric 의미 일치 여부, 전이 가능성 순서로 검토했다. 10개 PDF, 2개 데이터 패키지, 1개 소스 아카이브, 3개 문서/데이터 파일은 내용 또는 구조를 검토했다. PDF 확장자를 가진 2개 파일은 동일한 접근 차단 HTML이므로 원문 검토 완료로 간주하지 않았다.

이번 검토는 metric 정의, 측정 한계, 품질 게이트 원칙, Human Behavior Rubric 초안, 파일럿 검증 절차를 보강한다. 실제 사용자 임계값, 점수 구간, 축 가중치, 종합 가중치, 채용 판단은 만들거나 승인하지 않았다. 모든 gap은 production blocking 상태이며 최종 상태는 `scoring_gap_evidence_research_ready_with_access_limitations`이다.

## 검토 방법

- 확보 목록의 18개 자료만 대상으로 SHA-256, 크기, 형식 signature, 빈 파일 여부를 확인했다.
- PDF는 텍스트 추출과 핵심 페이지 렌더링을 함께 확인했다.
- 아카이브는 경로 안전성, 멤버 구조, 문서 및 제한된 샘플을 검토했으며 코드는 실행하지 않았다.
- 원문 통계, 모델 성능, 알고리즘 파라미터, 방송 표준값을 Face-Fit 행동 경계로 바꾸지 않았다.
- Head Pose와 Eye Gaze, 3D depth posture와 2D RGB shoulder metric, programme loudness와 browser dBFS를 서로 같은 측정으로 취급하지 않았다.
- 원문, 원시 CSV, 개인/평가자 행, 미디어, transcript, 로컬 경로는 저장소 산출물에 포함하지 않았다.

## 자료별 판정

| Evidence ID | 자료 | 검토 상태 | 채택 용도 | 핵심 제한 |
|---|---|---|---|---|
| GAP_DATA_001 | Seoul Corpus readme/manual/paper package | 전체 패키지 검토 | 한국어 corpus 설계, annotation 맥락 | 자연발화 corpus이며 면접 답변 경계가 아님 |
| GAP_DATA_002 | Seoul Corpus TextGrid labels | 구조 및 제한 샘플 검토 | timing annotation과 변환 검증 설계 | Face-Fit STT word gap 정의와 불일치 |
| GAP_SPEECH_003 | KsponSpeech paper | 원문 검토 | 한국어 비유창성 표기와 corpus 맥락 | 대화 corpus이며 자동 filler 감점 근거가 아님 |
| GAP_DATA_004 | KsponSpeech preprocessing code | 정적 검토, 미실행 | preprocessing 한계 | interjection 제거 로직을 filler 검증에 직접 사용할 수 없음 |
| GAP_FILLER_003 | FillerSpeech | 원문 검토 | filler annotation 연구 맥락 | 영어 TTS 목적이며 pitch/duration group은 행동 경계가 아님 |
| GAP_FILLER_004 | PodcastFillers | 원문 검토 | candidate+human review 설계 | 영어 podcast이며 문맥 false positive 검토가 필수 |
| GAP_DATA_007 | TalkTrack annotation guideline | 전체 문서 검토 | filler/repair human correction 절차 | 통역 발화 맥락이며 Face-Fit IAA가 없음 |
| GAP_RUBRIC_002 | PSCR+ rating CSV | 구조·범위·집계 검토 | reliability 분석 예시 | 4개 발표의 소규모 원시 평정으로 일반화 불가 |
| GAP_RUBRIC_003 | PSCR+ README | 전체 문서 검토 | 분석 재현 조건 | Face-Fit scale과 설계에 맞춘 통계 선택이 별도 필요 |
| GAP_GAZE_001 | Off-camera gaze online interview | 접근 제한 | 메타데이터와 접근 한계만 | 확보 파일이 PDF가 아닌 HTML challenge |
| GAP_GAZE_002 | Webcam gaze under natural head movement | 원문 검토 | head와 ocular gaze 구분, 측정 오차 | gaze tracker 연구이며 면접 행동 경계가 없음 |
| GAP_GAZE_003 | Gaze-in-Wild | 원문 검토 | eye/head 분리와 annotation 설계 | mobile eye tracker 일상 과제로 webcam 면접과 다름 |
| GAP_BODY_003 | RULA video/IMU sitting posture | 접근 제한 | 메타데이터와 접근 한계만 | 확보 파일이 PDF가 아닌 HTML challenge |
| GAP_BODY_004 | SitPose | 원문 검토 | seated posture pilot 설계 맥락 | Azure Kinect 3D joints와 Face-Fit 2D RGB가 다름 |
| GAP_AUDIO_001 | EBU Tech 3343 | 원문 검토 | audio quality 용어와 측정 주의 | 방송 programme normalisation은 말하기 행동 점수가 아님 |
| GAP_AUDIO_002 | ITU-R BS.1770-5 | 원문 검토 | loudness/true-peak algorithm 맥락 | RMS dBFS 또는 clipping ratio와 동일하지 않음 |
| GAP_METHOD_001 | Multimodal presentation competence | 원문 검토 | rater training, ICC, multimodal validation 설계 | 학생 발표 모델의 계수·성능은 Face-Fit 가중치가 아님 |
| GAP_METHOD_002 | ROC Speak | 원문 검토 | 반복 세션과 human feedback pilot 설계 | 시스템 효과 연구이며 metric cutoff가 없음 |

## Gap 판정

16개 gap 중 닫힌 항목은 없다.

- `PARTIALLY_SUPPORTED` 4개: 한국어 발화 속도, 조음 속도, pause, filler. 정의와 annotation 자원은 확보했지만 면접 task, STT semantics, human criterion 전이가 검증되지 않았다.
- `METHOD_DEFINED` 4개: head pose와 eye gaze 구분, human rubric, inter-rater reliability, validation design. 절차 초안은 만들 수 있으나 Face-Fit pilot 결과가 없다.
- `QUALITY_ONLY` 1개: microphone loudness normalisation. 행동 점수가 아니라 capture quality와 비교 가능성 문제로만 사용한다.
- `PILOT_REQUIRED` 4개: shoulder-center movement, multi-session distribution, threshold sensitivity, axis-weight validation.
- `ACCESS_LIMITED` 3개: webcam head-pose behavior, seated shoulder posture, bias/fairness validation. 핵심 자료 접근 실패 또는 전이 불가능성이 남아 있다.

## Metric Mapping 및 Threshold Readiness

등록된 18개 metric을 Stage 32 자료에 다시 매핑했다. 새 관계는 모두 `PROXY` 또는 `NOT_APPLICABLE`이며 `DIRECT`로 승격한 metric은 없다. Stage 31 readiness는 18개 모두 유지했다.

- Head metric은 gaze 자료로부터 측정·구성개념 한계만 채택했다. Eye contact나 attention을 추론하지 않는다.
- Posture metric은 depth-sensor 연구를 2D webcam metric의 직접 근거로 사용하지 않았다.
- Korean speech 자료는 annotation과 pilot 설계를 보강하지만 WPM, pause, filler의 점수 경계를 제공하지 않는다.
- EBU/ITU 자료는 audio quality 문맥에만 연결했다.
- F0 range는 계속 scoring 제외 상태다.
- threshold profile, metric/axis/overall weight, production approval은 모두 생성하지 않았다.

## Human Behavior Rubric v1

10개 초안 항목은 답변 단위의 직접 관찰 가능한 행동과 관찰 가능성만 다룬다. 각 항목은 `LEVEL_1`부터 `LEVEL_4`까지의 서술 anchor와 `NOT_OBSERVABLE`, `INSUFFICIENT_DATA`를 갖는다. level은 향후 독립 평정용 ordinal label이며 자동 점수가 아니다.

Personality, emotion, anxiety, confidence, deception, gender, health, job fit, hiring recommendation 추론은 금지한다. Head orientation을 eye contact로, 움직임 없음이나 높은 음량을 더 좋은 의사소통으로 간주하지 않는다.

## Pilot Data Collection Spec v1

파일럿 설계는 다음을 필수 gate로 둔다.

- 연구 동의, 개인정보·보존 정책, protocol/rubric preregistration
- 독립 rater training, blind rating, 원 평정 보존, 별도 adjudication
- 반복 세션과 device/environment strata
- metric·axis·device·환경별 missingness 및 availability 보고
- ordinal scale에 맞는 inter-rater reliability와 불확실성
- test-retest, construct validity, fairness/accessibility, participant-level held-out 검증
- threshold sensitivity와 axis weight의 별도 사전등록

표본 수, 최소 rater 수, 반복 세션 수, reliability 합격 기준, quality gate 값은 근거 분석 전까지 `TBD`다. 설계 문서는 데이터 수집 자체를 승인하지 않는다.

## 실제 어댑터 Fail-closed 검증

기존 실제 산출물 `SES_000001`을 읽기 전용으로 사용했다.

- Speech: 4개 답변에서 40개 metric row
- Vision: 4개 answer interval에서 24개 behavior metric row
- Quality Gate: 64개 row 모두 평가
- 결과: `scoringAvailable=false`, `score=null`
- transcript text, media, participant/rater raw row, metric 원시값은 보고서나 저장소에 복사하지 않음

## 남은 Production 차단 조건

1. 접근 제한 원문의 합법적이고 검증 가능한 사본 확보
2. 승인된 연구·개인정보 절차와 잠금된 protocol/rubric
3. 충분한 독립 평정과 inter-rater/test-retest 결과
4. device/environment 및 fairness/accessibility missingness audit
5. construct validity와 participant-level held-out validation
6. 별도 승인된 threshold sensitivity 및 axis-weight 연구
7. 독립 검토와 fail-closed production verification

이 조건이 충족되기 전에는 실제 사용자 점수나 production scoring을 제공할 수 없다.
