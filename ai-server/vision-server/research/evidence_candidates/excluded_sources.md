# Face-Fit Stage 12 제외 자료 기록

상태: `REVIEW_REQUIRED`

이 문서는 검색 과정에서 검토했지만 핵심 Evidence Source 수나 운영 threshold 후보에 포함하지 않은 자료를 기록한다. 제외는 논문의 일반적 품질 평가가 아니라 이번 Face-Fit 범위와의 적합성 판단이다.

| 자료 | 판정 | 제외 또는 제한 사유 |
|---|---|---|
| [Reliability and accuracy of 2D lower limb joint angles during a standing-up motion assessed with OpenPose and DeepLabCut](https://doi.org/10.1016/j.medntd.2022.100188) | `EXCLUDED` | 단일 카메라 2D 검증이라는 장점은 있으나 대상이 엉덩이·무릎과 의자 일어서기다. Face-Fit 얼굴·어깨 범위와 불일치하고, 보고된 10도 이하 오차를 어깨 또는 Head Pose에 전용할 수 없다. |
| [The accuracy of markerless motion capture combined with computer vision techniques for measuring running kinematics](https://doi.org/10.1111/sms.14319) | `EXCLUDED` | 달리기의 엉덩이·무릎·발목 시상면 운동학이 중심이며 Face-Fit이 사용하지 않는 하체 지표다. |
| [Assessing single camera markerless motion capture with OpenSim inverse kinematics during upper limb activities of daily living](https://pubmed.ncbi.nlm.nih.gov/40911347/) | `EXCLUDED` | 2025년 상지 활동 연구지만 Azure Kinect depth와 OpenSim 3D 역운동학, 팔꿈치·손목·몸통 좌표계를 사용한다. Face-Fit의 2D 양쪽 어깨선 정의와 동일하지 않다. |
| [Evaluation of natural head position over five minutes: A comparison between an instantaneous and a five-minute analysis with an inertial measurement unit](https://pmc.ncbi.nlm.nih.gov/articles/PMC9304234/) | `EXCLUDED` | 자연 머리 위치의 반복성에는 유용하지만 치과/두개안면 맥락의 IMU 연구이며 면접 행동 평가가 아니다. 표본 분포를 면접 자세의 정상 범위로 오인할 위험이 크다. |
| [A Multimodal Corpus for the Assessment of Public Speaking Ability and Anxiety](https://aclanthology.org/L16-1078/) | `EXCLUDED_FROM_INDEPENDENT_COUNT` | 공개 코퍼스 자료로서 유용하지만 `SRC_PUB_002` Wörtwein et al.과 같은 연구 프로그램 및 중첩 코퍼스를 다룬다. 자료 수를 중복으로 채우지 않기 위해 독립 보조 근거 수에서는 제외했다. 불안·성격 추론도 Face-Fit 금지 범위다. |
| [Designing an automated assessment of public speaking skills using multimodal cues](https://doi.org/10.18608/jla.2016.32.13) | `EXCLUDED_FROM_INDEPENDENT_COUNT` | `SRC_PUB_001` Chen et al. 2014의 ETS 발표 코퍼스와 방법을 확장한 후속 논문이다. 독립 표본 근거처럼 이중 계산하지 않았다. |
| [Enhancing Public Speaking Skills—An Evaluation of the Presentation Trainer in the Wild](https://doi.org/10.1007/978-3-319-45153-4_20) | `EXCLUDED_FROM_CORE_EVIDENCE` | 9명 현장 탐색 연구이고 기술 실패로 마지막 3개 최종 발표만 시스템이 측정했다. 학습도구 사용성·현장 도입이 중심이며 Face-Fit 호환 Head/Shoulder 수치가 없다. |
| [Evaluating Multimodal Behavioral Features for Public Speaking Assessment in Virtual Reality](https://doi.org/10.1145/3717511.3749301) | `EXCLUDED_FROM_CORE_EVIDENCE` | 2025년 최신 연구이나 Meta Quest Pro 기반 VR 발표 자료다. Face-Fit 단일 RGB 웹캠과 센서·맥락 차이가 크며, 극단 집단 분류 성능을 정상/비정상 자세 기준으로 오해할 위험이 있다. |
| 척추측만증, 거북목, 골반 비대칭, Trendelenburg 검사 등 의료 진단 자세 논문 | `EXCLUDED` | 질환 진단 목적이고 척추·골반·엉덩이·하체를 사용한다. Face-Fit은 해당 구조나 질환을 측정·추론하지 않는다. |
| MRI/MEG/방사선치료의 머리 움직임 제외 기준 논문 | `EXCLUDED` | 영상 아티팩트 또는 치료 정렬 오차 제어를 위한 경계다. 의사소통 행동이나 면접 평가 기준이 아니다. |
| 제품 판매 페이지, 개인 블로그, 출처 없는 “좋은 자세 각도” 콘텐츠 | `EXCLUDED` | 원 논문, 표본, 측정법, 원문 수치 위치를 검증할 수 없어 핵심 근거로 사용할 수 없다. |
| Reddit·질문답변 사이트의 MediaPipe 임계값 제안 | `EXCLUDED` | 경험적 제안 또는 임의 설정이며 동료평가·검증 자료가 아니다. |

## 제외 원칙

- 신체 부위 이름에 “shoulder”가 들어 있어도 좌우 어깨선을 측정하지 않으면 Face-Fit shoulder tilt의 직접 근거로 보지 않았다.
- 측정 장비의 허용 오차, 영상 아티팩트 제거 기준, 의료적 정렬 기준은 면접 행동 threshold에서 제외했다.
- 동일 또는 중첩 코퍼스의 후속 논문은 출처로 참고할 수 있지만 독립 연구 수로 중복 계산하지 않았다.
- 원문에서 숫자와 위치를 확인하지 못한 검색 스니펫 수치는 Evidence Record로 만들지 않았다.
