# Face-Fit 비전 분석 Stage 12 연구 보고서

상태: `REVIEW_REQUIRED`  
작성일: 2026-07-29  
적용 범위: 연구 검토용 후보 자료

> 이 보고서는 운영 threshold, 실제 사용자 점수, 합격 가능성, 성격·불안·자신감 추론을 승인하지 않는다. Stage 11의 Metric Registry, Evidence Profile, Threshold Profile, Scoring Contract와 `TEST_FIXTURE`는 변경하지 않았다.

## 1. 결론

현재 문헌으로 Face-Fit의 `relative_* ABS_P95` 지표에 바로 적용할 운영 threshold를 만들 수 없다.

- 취업 면접에서 비언어 행동과 평가의 관계는 존재한다. 특히 63개 연구, N=4,868의 메타분석에서 broad **head movement**와 면접 평가의 수정 상관은 `ρ=.43`이었다. 그러나 이 construct는 yaw/pitch/roll, 각도, 방향, 세션 baseline 또는 p95를 구분하지 않는다.
- 실제 면접 영상에서 applicant optical flow와 hirability 평가가 연관된 연구가 있지만, 이는 얼굴·상체 전체의 영상 움직임이며 Face-Fit의 shoulder-center velocity와 동일하지 않다.
- Head Pose 기술 논문은 축별 오차를 제공한다. 이 수치는 **측정 정확도**이지 좋은/나쁜 면접 태도의 경계가 아니다.
- 좌우 어깨를 연결한 선의 기울기, 세션 baseline 대비 상대 어깨 기울기, `ABS_P95`를 면접 평가와 직접 연결한 연구는 확인하지 못했다.
- 품질 availability ratio는 행동 평가가 아니라 캡처·검출 품질 지표다. 비언어 행동 논문으로 점수화해서는 안 된다.

따라서 이번 단계의 운영 threshold 후보는 **0건**, 모든 Evidence/Mapping 상태는 `REVIEW_REQUIRED`다.

## 2. 검색 방법

### 사용 출처

- IEEE Xplore 및 IEEE/CVF Open Access
- ACM Digital Library와 대학 기관 저장소
- Wiley Online Library
- PubMed/PubMed Central
- PLOS ONE, Frontiers, MDPI
- ETS 공식 연구 페이지
- 저자·대학·연구기관이 제공한 원문 PDF

### 주요 검색어

- `employment interview nonverbal behavior head movement hireability`
- `automated video interview webcam facial head gesture`
- `public speaking assessment head movement body posture multimodal`
- `head pose estimation yaw pitch roll single camera validation`
- `MediaPipe OpenFace head pose accuracy`
- `2D markerless shoulder upper body camera angle OpenPose`
- `systematic review meta-analysis nonverbal job interview`

### 기간

1999-2026년의 대표·기초 연구와 최신 연구를 함께 검토했다. 2000년 이후 연구를 중심으로 하되 1999년 DeGroot와 Motowidlo의 대표 면접 연구를 포함했다.

### 포함 기준

- 동료평가 논문 또는 공신력 있는 기관의 원문
- 목적, 표본, 측정법 또는 리뷰 범위가 확인됨
- 면접 비언어 행동, 발표 보조 근거, Head Pose 측정, 2D/상반신 측정 중 하나에 해당
- 정량 결과는 원문 표·절·초록에서 위치를 확인할 수 있음
- Face-Fit에 직접 적용할 수 없더라도 그 한계를 명시적으로 설명할 수 있음

### 제외 기준

- 의료 진단, 척추·골반·하체 중심
- 제품·블로그·출처 없는 수치
- 중복 코퍼스를 독립 연구처럼 계산한 자료
- 원문에서 수치와 위치를 확인할 수 없는 주장
- MRI 아티팩트, 방사선치료 정렬 등 의사소통 행동과 다른 threshold

정량값은 원문 또는 공식 저자·기관 원문에서 확인한 것만 Evidence Record로 만들었다. 보고되지 않은 항목은 `NOT_REPORTED`로 유지했다.

## 3. 수집 결과

| 구분 | 수 |
|---|---:|
| 최종 포함 Source | 20 |
| 면접 맥락 Source | 7 |
| 그중 개별 표본의 정량 비언어/영상 연구 | 4 |
| 발표 보조 Source | 4 |
| Head Pose 측정·검증 Source | 5 |
| 2D/상반신 측정 Source | 4 |
| Meta-analysis | 1 |
| Scoping review | 1 |
| 그 밖의 narrative/quantitative review 또는 survey | 3 |
| Evidence Record 후보 | 30 |
| 기존 Stage 11 metric에 대한 Mapping 후보 | 28 |
| 직접 Mapping | 0 |
| 운영 Threshold 후보 | 0 |
| 비운영 수치 참고 항목 | 23 |
| Association-only Evidence Record | 7 |
| Measurement-accuracy Evidence Record | 8 |
| 열린 충돌 | 10 |

포함 범주의 합은 중복되지 않도록 구성했다. `SRC_INT_005`는 면접 범주이면서 meta-analysis이고, `SRC_PUB_004`는 발표 보조 범주이면서 scoping review다. 따라서 formal evidence synthesis를 2편 포함했다.

## 4. 논문별 요약

표의 “Metric”은 기존 Stage 11 ID만 표기한다. `—`는 직접 또는 타당한 proxy 매핑이 없다는 뜻이다.

| Source ID | 연구 맥락·표본 | 촬영·측정 환경 / FPS | 부위·지표 | 핵심 정량 결과 | Threshold 유형 | Metric / Mapping / 적용성 | 우선순위·한계·원문 위치 |
|---|---|---|---|---|---|---|---|
| `SRC_INT_001` | 취업 면접; Study 1 N=60, Study 2 N=110 managers | videotape; 해상도·FPS `NOT_REPORTED`; 수동 코딩 | 외모·미소·gaze·손 움직임·body orientation composite | visual composite–interviewer judgment `r=.21`; performance `r=.14, p<.07` | `ASSOCIATION_ONLY` | shoulder velocity / `COMPOSITE` / `INDIRECT` | P1; composite와 민감한 appearance 포함; Abstract, pp.986, 991, Table 2 |
| `SRC_INT_002` | 실제 마케팅 채용 면접; N=62 | 2 HD cameras, 1280×960, 26.6 FPS, quasi-frontal upper body | optical flow, WMEI, 수동 ratings | applicant vertical flow `r=.330`; WMEI avg `r=.280`; best ridge `R²=.362` | `ASSOCIATION_ONLY` 또는 model performance | shoulder velocity / `PROXY` / `PARTIAL-INDIRECT` | P1; landmark shoulder가 아님; Table III p.1023, Sec. V-C pp.1024-1025 |
| `SRC_INT_003` | MIT mock internship interview; 69명, 138 sessions | 2D video; 세부 FPS `NOT_REPORTED` | smile, facial points, head gesture/nod, 음성·언어 | overall/hiring prediction `r>.62`; hiring AUC `.80` | `NO_NUMERIC_THRESHOLD` | pitch / `PROXY` / `REVIEW_REQUIRED` | P1; nod 정의·각도 없음, composite model; Table 5 p.200 |
| `SRC_INT_004` | 비동기 온라인 video interview; 260명, 1,891 videos | participant webcam, 480p, 30 FPS, uncontrolled | face expression, audio, text; 5 raters | hiring-rating ICC `.79` | `NO_NUMERIC_THRESHOLD` | — | P1; 단일 웹캠 환경은 유사하나 Head/Shoulder 수치 없음; Table II p.506 |
| `SRC_INT_005` | 63 interview studies, N=4,868 | 연구별 상이 | broad nonverbal cues | head movement `ρ=.43`, eye contact `ρ=.45`, professional appearance `ρ=.62` | `ASSOCIATION_ONLY` | yaw/pitch/roll / `PROXY` / `PARTIAL-REVIEW_REQUIRED` | P1; 축·방향·각도·p95 없음; Summary, Results pp.142-147 |
| `SRC_INT_006` | structured employment interview review | 연구별 상이 | 구조화·bias·IM·rating 등 8 topics | Face-Fit 호환 수치 없음 | `NO_NUMERIC_THRESHOLD` | — | P1; 설계·타당도 맥락만 제공; Abstract, pp.241-293 |
| `SRC_INT_007` | comprehensive interview review | 278 studies | 사회·인지·개인차·측정·결과 요인 | review count 278 | `NO_NUMERIC_THRESHOLD` | — | P1; 단일 행동 점수화에 반대되는 다요인 맥락; Abstract pp.1-3 |
| `SRC_PUB_001` | public speaking; 17 speakers, 56 presentations | JVC HD + Kinect v1, 약 6 ft; FPS `NOT_REPORTED` | 48 3D joints, head/body motion | visual-only `r=.202`; multimodal best `r=.447` | `ASSOCIATION_ONLY` / model performance | shoulder velocity / `COMPOSITE` / `INDIRECT` | P2; 3D full-body, 소표본; Table 2 p.202 |
| `SRC_PUB_002` | public speaking; 47 adults | Logitech webcam + Kinect + mic; FPS `NOT_REPORTED` | CLNF head orientation, OKAO gaze, Kinect gestures | multimodal overall `r=.745`; gaze-angle boundary 숫자는 미보고 | `NO_NUMERIC_THRESHOLD` | yaw/pitch 및 shoulder velocity / `PROXY-COMPOSITE` / `INDIRECT` | P2; virtual audience와 composite model; Visual Behavior p.46, Results p.48 |
| `SRC_PUB_003` | public-speaking expert study | prototype sensor detail `NOT_REPORTED` | nonverbal practices | 131 practices | `NO_NUMERIC_THRESHOLD` | shoulder tilt / `PROXY` / `INDIRECT` | P2; 정성 연구이며 valid assessment model 부족을 저자가 지적; Abstract p.164 |
| `SRC_PUB_004` | adult public-speaking scoping review; 35 studies | human evaluator observation; technological assessment 제외 | eye contact, gesture, posture, head movement 등 평가 indicator | non-validated instrument 26편 중 posture 11편(42.3%), head movement 2편(7.7%) | `NO_NUMERIC_THRESHOLD` | shoulder tilt / `PROXY` / `INDIRECT` | P2; indicator 사용 빈도이지 효과·threshold가 아님; Results Fig.1/Table 3, Discussion |
| `SRC_HEAD_001` | Head Pose survey | 90 papers | 다양한 2D/3D head pose methods | review count 90 | `NO_NUMERIC_THRESHOLD` | — | P3; 측정법 survey, 면접 행동 아님; Abstract p.607 |
| `SRC_HEAD_002` | AFLW2000/BIWI benchmark | monocular RGB | Hopenet yaw/pitch/roll | AFLW overall MAE `6.155°`; BIWI `4.895°` | `MEASUREMENT_ACCURACY` | yaw/pitch/roll / `PROXY` / `INDIRECT` | P3; 다른 모델·absolute benchmark; Tables 1-2 pp.6-7 |
| `SRC_HEAD_003` | AFLW2000 benchmark | single RGB image | FSA-Net yaw/pitch/roll | FSA-Caps-Fusion MAE yaw `4.50°`, pitch `6.08°`, roll `4.64°`, mean `5.07°` | `MEASUREMENT_ACCURACY` | yaw/pitch/roll / `PROXY` / `INDIRECT` | P3; single-image benchmark; Table 1 p.7 |
| `SRC_HEAD_004` | facial-analysis toolkit | dataset별 RGB image/video | OpenFace 2.0 head pose, gaze, AU | Face-Fit 호환 정확도 수치 없음 | `NO_NUMERIC_THRESHOLD` | — | P3; toolkit capability source; Abstract/System pp.59-61 |
| `SRC_HEAD_005` | controlled head movement, 24 video trials | RGB + OptiTrack; FPS `NOT_REPORTED` | MediaPipe/OpenFace/3DDFA yaw, pitch, roll | MediaPipe bias yaw `11.00°`, pitch `7.00°`, roll `1.37°` | `MEASUREMENT_ACCURACY` | corresponding axes / `PROXY` / `PARTIAL` | P3; 임상 측정오차이며 5 FPS Face-Fit과 다름; Tables 2-3, Sec.3 |
| `SRC_POSE_001` | COCO/MPII pose benchmark | single RGB images | 2D body keypoints, person association | Face-Fit shoulder-line 수치 없음 | `NO_NUMERIC_THRESHOLD` | shoulder tilt / `UNSUPPORTED` / `NOT_APPLICABLE` | P3; 방법 기반 논문; Abstract/Method pp.7291-7294 |
| `SRC_POSE_002` | biomechanics; N=2 | 5 video cameras; 1920×1080 120 Hz 또는 4K 30 Hz; 16-camera reference | 3D full-body joints | MAE의 47% <20 mm, 80% <30 mm, 10% >40 mm | `MEASUREMENT_ACCURACY` | shoulder velocity / `UNSUPPORTED` / `NOT_APPLICABLE` | P3; 3D multi-camera, N=2, 단위 불일치; Abstract/Discussion/Fig.3 |
| `SRC_POSE_003` | over-ground walking; N=15 | frontal+sagittal machine cameras + 15-camera MoCap; FPS `NOT_REPORTED` | OpenPose 25 keypoints, gait angles | shoulder-line tilt 수치 없음; occluded hip/knee agreement 저하 | `NO_NUMERIC_THRESHOLD` | shoulder tilt / `UNSUPPORTED` / `NOT_APPLICABLE` | P3; 하체 각도 중심; Abstract, Methods 2.2-2.4, Discussion |
| `SRC_POSE_004` | front lunge; N=20 | 4 iPad RGB, 1194×834, mean 43±2.6 FPS; 12-camera Vicon | OpenPose shoulder flexion | shoulder-flexion RMSE 23.63°-36.48° across views | `MEASUREMENT_ACCURACY` | shoulder tilt / `UNSUPPORTED` / `NOT_APPLICABLE` | P3; flexion은 좌우 shoulder line이 아님; Table 3, pp.9-12 |

## 5. 지표별 근거 판단

### 5.1 Head yaw

- 관련 근거: `SRC_INT_005`의 broad head movement association, `SRC_HEAD_002/003/005`의 기술 정확도.
- 측정 방법: 관찰 코딩, 단일 RGB CNN, MediaPipe/OptiTrack 비교가 혼재한다.
- 확인된 수치: broad head movement `ρ=.43`; Hopenet/FSA/MediaPipe yaw 오차.
- threshold: 없음.
- 적용 가능성: 인터뷰 construct에는 `PROXY`, 기술 정확도에는 `PARTIAL`; Face-Fit relative yaw `ABS_P95`에는 `DIRECT` 0건.
- 충돌: broad movement와 axis-specific error의 statistic/construct가 다르고, 알고리즘·데이터셋별 오차가 다르다.

### 5.2 Head pitch

- nod/head gesture 연구가 있으나 각도, 방향, 빈도, duration, p95가 보고되지 않았다.
- MediaPipe validation에서 pitch bias `7.00°`, SD `10.22°`가 보고됐지만 이는 측정오차다.
- eye contact를 pitch로 치환할 수 없다.
- 운영 threshold는 없다.

### 5.3 Head roll

- 면접 메타분석의 head movement 안에 roll이 포함됐는지 분리되지 않는다.
- MediaPipe controlled validation의 roll bias `1.37°`는 상대적으로 작았지만 좋은 자세 기준이 아니다.
- Face-Fit relative roll `ABS_P95` 직접 근거는 없다.

### 5.4 Shoulder tilt

- 좌우 어깨 landmark를 연결한 선의 각도와 면접 평가를 함께 연구한 포함 논문은 0편이다.
- `SRC_POSE_004`의 shoulder flexion은 어깨-팔꿈치 벡터와 몸통 벡터의 각도다. Face-Fit shoulder-line tilt와 해부학적·수학적으로 다르다.
- `SRC_POSE_003`은 shoulder 위치를 processing에 사용하지만 검증 outcome은 gait의 hip/knee 등이다.
- 매핑은 `UNSUPPORTED` 또는 정성 posture의 `PROXY`만 가능하다.

### 5.5 Shoulder movement and stability

- 실제 면접의 optical flow/WMEI가 가장 가까운 근거다.
- optical flow, motion energy, Kinect 3D gesture, 3D joint-position MAE는 `NORM_PER_SEC`로 변환할 수 없다.
- shoulder-center velocity의 방향이나 좋은 범위를 제시한 연구는 없다.
- 자체 데이터에서 Face-Fit 단위로 검증해야 한다.

### 5.6 Head–shoulder alignment proxy

- `POSTURE_RELATIVE_NOSE_OFFSET_X_ABS_P95_NORM`과 동일한 정의를 사용한 연구를 찾지 못했다.
- gaze, body orientation, head pose를 nose–shoulder offset으로 전용하는 것은 construct와 단위가 모두 다르다.
- 현재 판정은 `UNSUPPORTED`; 연구·전문가 라벨이 새로 필요하다.

### 5.7 Quality availability

- `QUALITY_HEAD_AVAILABILITY_RATIO`, `QUALITY_POSTURE_AVAILABILITY_RATIO`는 행동 품질이 아니라 검출·캡처 완전성이다.
- 행동 논문에서 threshold를 가져오지 않는다.
- 별도 failure-mode, 기기, 조명, 피부톤, 안경/마스크, 움직임, 보조기기, 네트워크·압축 조건으로 engineering gate를 검증해야 한다.

## 6. Threshold 판정

### 실제 운영 threshold 후보

| Evidence ID | Face-Fit Metric | 원 수치 | 단위 | 기준 유형 | Mapping | Applicability | 바로 적용 가능 |
|---|---|---:|---|---|---|---|---|
| 없음 | — | — | — | — | — | — | `NO` |

Hammadi et al.의 5°·10° tolerable error levels는 estimator가 특정 angle range에서 얼마만큼 버티는지 분석하기 위한 **measurement-error criteria**다. 면접 태도 category boundary가 아니므로 위 표에 넣지 않았다.

### Threshold로 직접 사용할 수 없는 대표 수치

| Evidence ID | Metric 후보 | 통계 유형 | 결과 | 의미 | 직접 threshold로 사용할 수 없는 이유 |
|---|---|---|---|---|---|
| `EVD_INT_005_01` | yaw/pitch/roll | meta-analytic association | `ρ=.43` | broad head movement와 면접 평가가 연관됨 | 축·각도·방향·p95 없음 |
| `EVD_INT_002_01` | shoulder velocity | association | `r=.330` | applicant image motion이 일부 평가와 연관됨 | optical flow와 landmark velocity의 단위·정의 불일치 |
| `EVD_INT_001_01` | upper-body motion proxy | association | `r=.21` | visual composite와 interviewer judgment 연관 | 외모·미소·gaze·손·orientation composite |
| `EVD_PUB_001_01` | shoulder movement proxy | association | `r=.202` | visual model과 발표 점수의 약한 연관 | Kinect/full-body/public-speaking |
| `EVD_HEAD_005_01` | yaw | measurement error | `11.00°`, SD `10.65°` | controlled task의 MediaPipe yaw bias | 모델 오차이지 행동 경계가 아님 |
| `EVD_HEAD_005_02` | pitch | measurement error | `7.00°`, SD `10.22°` | controlled task의 MediaPipe pitch bias | 모델 오차이지 행동 경계가 아님 |
| `EVD_HEAD_005_03` | roll | measurement error | `1.37°`, SD `2.44°` | controlled task의 MediaPipe roll bias | 작은 오차도 좋은 자세를 뜻하지 않음 |
| `EVD_POSE_004_01` | shoulder tilt 후보 | measurement error | RMSE `23.63°-36.48°` | OpenPose shoulder flexion의 view sensitivity | 다른 해부학적 각도 |

전체 비운영 수치 목록은 `threshold_candidates.json`에 보존했다.

## 7. Applicability 및 Mapping 결과

기존 Stage 11 metric에 대한 28개 mapping 후보:

| Applicability | 수 |
|---|---:|
| `DIRECT` | 0 |
| `PARTIAL` | 6 |
| `INDIRECT` | 12 |
| `REVIEW_REQUIRED` | 6 |
| `NOT_APPLICABLE` | 4 |

| Mapping Type | 수 |
|---|---:|
| `DIRECT` | 0 |
| `UNIT_CONVERSION` | 0 |
| `PROXY` | 21 |
| `DERIVED` | 0 |
| `COMPOSITE` | 3 |
| `UNSUPPORTED` | 4 |

연구 요청에 제시됐지만 Stage 11 registry에 없는 median/STD/MAD, shoulder displacement, tilt velocity, face offset, 추가 quality metric 이름은 `proposed_metric_ids_not_added_to_registry`에만 기록했다. registry에는 추가하지 않았다.

## 8. 충돌과 미해결 위험

10개 충돌을 모두 `OPEN` 또는 `REVIEW_REQUIRED`로 유지했다.

- broad head movement association vs yaw/pitch/roll measurement error
- association 방향 부재 vs absolute p95 penalty 설계
- eye contact vs head-orientation proxy
- real interview optical flow vs public-speaking Kinect body features
- optical flow/WMEI/mm vs normalized velocity unit
- shoulder flexion/gait angle vs shoulder-line tilt
- 알고리즘·데이터셋별 Head Pose error 차이
- 모집단·직무·면접 방식 차이
- behavior evidence vs availability quality gate
- 이질적이고 다수가 비검증인 human-rating instrument vs sensor-specific automated metric

결과를 평균 내거나 하나의 논문을 선택해 자동 해결하지 않았다.

## 9. 최종 연구 판단

1. **Head Pose에 실제 운영 threshold로 사용할 직접 근거가 있는가?**  
   없다. 면접 연구는 broad head movement 또는 gaze를 보고하고, 기술 연구는 estimator error를 보고한다. Face-Fit의 세션 상대 yaw/pitch/roll `ABS_P95`와 동일한 운영 construct가 아니다.

2. **Shoulder tilt에 직접 적용 가능한 근거가 있는가?**  
   없다. 포함된 2D 논문의 shoulder flexion은 좌우 shoulder-line tilt가 아니며, 면접 연구는 body orientation 또는 전체 upper-body motion을 사용한다.

3. **면접 상황에 직접 관련된 연구는 몇 편인가?**  
   7편이다. 이 가운데 개별 면접 표본의 정량 비언어/영상 연구는 4편, meta-analysis 1편, broader interview review 2편이다. 그러나 Face-Fit metric에 `DIRECT`로 적용 가능한 논문은 0편이다.

4. **발표 연구를 proxy로 사용해야 하는 지표는 무엇인가?**  
   head orientation의 audience-facing proxy와 broad shoulder/body movement다. `HEAD_RELATIVE_YAW/PITCH_ABS_P95_DEG`, `POSTURE_SHOULDER_CENTER_VELOCITY_P95_NORM_PER_SEC`에만 제한적 `PROXY/COMPOSITE` 검토가 가능하다. roll, shoulder-line tilt, nose/face–shoulder offset에 직접 전용할 수 없다.

5. **실제 threshold보다 분포·상관관계 근거만 있는 지표는 무엇인가?**  
   broad head movement, eye contact, upper-body visual motion, multimodal public-speaking performance다. Head Pose 축별 숫자는 행동 분포가 아니라 measurement accuracy다.

6. **논문 근거가 특히 부족한 Face-Fit 지표는 무엇인가?**  
   `POSTURE_RELATIVE_SHOULDER_TILT_ABS_P95_DEG`, `POSTURE_RELATIVE_NOSE_OFFSET_X_ABS_P95_NORM`, shoulder/face offset 파생 후보, quality availability ratio의 행동적 의미다. yaw/pitch/roll도 측정 근거는 있으나 면접 평가 construct 근거가 부족하다.

7. **새 데이터 수집과 전문가 라벨링이 필요한 지표는 무엇인가?**  
   모든 행동 지표가 필요하다. 우선순위는 Head Pose 3축, shoulder-line tilt, shoulder-center velocity, nose/face–shoulder alignment다. quality metrics는 전문가 인상 라벨이 아니라 detector failure ground truth가 필요하다.

8. **단일 논문으로 운영 기준을 만들 때의 위험은 무엇인가?**  
   센서·FPS·카메라 배치·단위·통계·모집단·직무·면접 형태 차이를 무시하게 된다. 사람의 면접 평가는 편향을 포함할 수 있고, 상관을 인과로 바꾸거나 모델 정확도를 행동 정상 범위로 오인할 수 있다. 장애, 문화, 신경다양성, 화면 배치, 보조기기와 촬영 환경에 대한 차별적 오류 위험도 있다.

## 10. 다음 단계 권장

1. 운영 scoring과 분리된 Face-Fit 연구용 데이터셋을 수집한다.
2. 원본 30 FPS 이상 영상과 Face-Fit 5 FPS 샘플을 동시에 보존해 sampling sensitivity를 평가한다.
3. yaw/pitch/roll은 calibrated 또는 독립 reference와 비교해 exact implementation error를 구한다.
4. shoulder-line tilt와 shoulder-center movement는 두 명 이상의 trained annotator 또는 calibrated landmark reference로 검증한다.
5. 면접 전문가가 전체 인상만 평가하지 않도록, 지표별 관찰 rubric와 “판단 불가” 옵션을 사전 정의한다.
6. 상관·비선형 관계·상호작용을 먼저 탐색하고 threshold는 사전등록된 held-out validation 없이는 만들지 않는다.
7. 직무, 언어, 문화, 성별, 장애·신경다양성, 기기, 해상도, 조명, 안경/마스크 및 화면 배치별 fairness/error 분석을 수행한다.
8. quality availability는 behavioral score와 분리하고, 일정 품질 미달 시 점수가 아니라 `insufficient_evidence`를 반환하도록 검토한다.
9. 전문가·법무·윤리·채용공정성 검토 후에도 자동 합격 판단에는 사용하지 않는다.

## 11. 주요 원문

- [Martín-Raugh et al., 2023 — job-interview nonverbal meta-analysis](https://onlinelibrary.wiley.com/doi/10.1002/job.2670)
- [Nguyen et al., 2014 — real employment interviews and nonverbal behavior](https://publications.idiap.ch/attachments/papers/2014/Nguyen_TMM_2014.pdf)
- [Naim et al., 2018 — automated interview performance](https://roc-hci.com/wp-content/uploads/tac16_job.pdf)
- [Chen et al., 2017 — large online video-interview corpus](https://hoques.com/Publications/2017/2017-ACII-Assessment-Chen-etal.pdf)
- [DeGroot & Motowidlo, 1999 — visual/vocal interview cues](https://doi.org/10.1037/0021-9010.84.6.986)
- [Levashina et al., 2014 — structured interview review](https://onlinelibrary.wiley.com/doi/10.1111/peps.12052)
- [Chen et al., 2014 — multimodal public-speaking assessment](https://www.ets.org/research/policy_research_reports/publications/article/2014/jtui.html)
- [Wörtwein et al., 2015 — multimodal public-speaking performance](https://publikationen.bibliothek.kit.edu/1000051017)
- [Scanferla et al., 2026 — adult public-speaking indicator scoping review](https://pubmed.ncbi.nlm.nih.gov/42054185/)
- [Hammadi et al., 2022 — MediaPipe/OpenFace/3DDFA head-pose validation](https://pmc.ncbi.nlm.nih.gov/articles/PMC9502716/)
- [Ruiz et al., 2018 — Hopenet head-pose benchmark](https://openaccess.thecvf.com/content_cvpr_2018_workshops/w41/html/Ruiz_Fine-Grained_Head_Pose_CVPR_2018_paper.html)
- [Yang et al., 2019 — FSA-Net head-pose benchmark](https://openaccess.thecvf.com/content_CVPR_2019/html/Yang_FSA-Net_Learning_Fine-Grained_Structure_Aggregation_for_Head_Pose_Estimation_From_CVPR_2019_paper.html)
- [Nakano et al., 2020 — OpenPose multi-camera accuracy](https://pmc.ncbi.nlm.nih.gov/articles/PMC7739760/)
- [Wade et al., 2023 — 2D frontal/sagittal markerless validation](https://pmc.ncbi.nlm.nih.gov/articles/PMC10635560/)
- [Baldinger et al., 2025 — camera-view effects on OpenPose](https://pmc.ncbi.nlm.nih.gov/articles/PMC11819822/)

## 12. 산출물 검증

- 5개 JSON 파일의 UTF-8 파싱 성공
- Source→Evidence 및 Evidence→Mapping 참조 누락 0건
- Mapping에 사용된 registry 외 metric ID 0건
- 상태가 `DRAFT`/`REVIEW_REQUIRED`를 벗어난 후보 0건
- `APPROVED` status/review_status 0건
- Stage 11 fixture contract smoke 실행 성공: `status=completed`, `real_user_score_generated=false`, `production_threshold_approved=false`
- 프로젝트 `.venv`와 시스템 Python에 `pytest` 모듈이 없어 전체 pytest suite는 실행하지 못했다. 패키지를 새로 설치하거나 lock 파일을 변경하지 않았다.

## 13. 산출물

- `source_candidates.json`: 20개 Source 후보와 연구·센서·표본 메타데이터
- `evidence_record_candidates.json`: 30개 수치/무수치 Evidence 후보
- `metric_mapping_candidates.json`: 기존 registry ID에만 연결한 28개 Mapping 후보와 미등록 metric 제안 목록
- `threshold_candidates.json`: 운영 후보 0건, 비운영 수치 참고 23건
- `evidence_conflicts.json`: 미해결 충돌 10건
- `excluded_sources.md`: 제외·중복·범위 불일치 자료

모든 산출물은 검토용이며 `APPROVED` 상태를 포함하지 않는다.
