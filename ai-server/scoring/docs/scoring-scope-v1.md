# Scoring scope V1

The Face-Fit Coaching Score is a practice-oriented behavior feedback score: it expresses how observed head-direction, posture, and speech-delivery measurements compare with a separately reviewed coaching profile. It is not a probability of hiring, candidate/job fit, work ability, personality, emotion, anxiety, confidence, deception, gender, health, disability, age, race, nationality, religion, region of origin, or appearance quality.

V1 supports `GAZE_HEAD`, `POSTURE`, and `SPEECH_DELIVERY`. Head Pose values are camera-dependent proxies, not eye tracking or eye-contact ratios. Posture values are 2D shoulder/head alignment proxies, not medical or character judgments. Speech values are physical/timing measurements, not content or psychological inference. `CONTENT`, `HIRING`, `PERSONALITY`, and `EMOTION` are unsupported.

Real-user scoring is disabled. The only executable profile contains synthetic boundaries and weights for calculator tests.

이 엔진의 구현 완료는 실제 사용자 점수가 승인되었다는 뜻이 아니다.
실제 Threshold와 Weight는 논문 Evidence 검토 및 다중 Session 검증 후 별도의 승인된 Profile로 제공한다.
