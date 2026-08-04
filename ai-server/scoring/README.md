# Face-Fit experimental scoring

This package implements a profile-driven **Face-Fit Coaching Score** engine for practice feedback about observable head-direction, upper-body posture, and speech-delivery measurements. It does not predict hiring success, job fit, work ability, personality, emotion, anxiety, confidence, deception, gender, or health. Head Pose is a proxy and is not eye tracking.

Supported V1 axes are `GAZE_HEAD`, `POSTURE`, and `SPEECH_DELIVERY`. `CONTENT`, `HIRING`, `PERSONALITY`, and `EMOTION` are unsupported. Overall scoring is disabled by default.

The engine is `EXPERIMENTAL`: synthetic profile `FACEFIT_EXPERIMENTAL_SCORE_V1` and synthetic session `SES_900001` exercise the calculator. Production and real-user scoring remain disabled; no public API endpoint is added and the existing integrated `scoringAvailable=false` contract is unchanged. `SES_000001` is explicitly blocked from synthetic scoring.

Run from the repository root with the Analysis Python environment:

```powershell
& $analysisPython ai-server\scoring\scripts\validate_scoring_package.py
& $analysisPython ai-server\scoring\scripts\run_experimental_scoring.py `
  --profile ai-server\scoring\fixtures\profiles\experimental-scoring-profile-v1.json `
  --input ai-server\scoring\fixtures\inputs\synthetic-scoring-input-v1.json `
  --allow-experimental
& $analysisPython -m unittest discover -s ai-server\scoring\tests -v
```

Generated output is atomic, strict JSON and is ignored by Git. Paper files under `evidence/` are also ignored.

이 엔진의 구현 완료는 실제 사용자 점수가 승인되었다는 뜻이 아니다.
실제 Threshold와 Weight는 논문 Evidence 검토 및 다중 Session 검증 후 별도의 승인된 Profile로 제공한다.
