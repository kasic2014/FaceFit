# Experimental scoring engine

## Status and safety boundary

`ai-server/scoring/README.md:3-7` describes a coaching calculator for observable head-direction, upper-body and speech-delivery measurements. It supports `GAZE_HEAD`, `POSTURE`, `SPEECH_DELIVERY`; `CONTENT`, hiring, personality and emotion are unsupported.

Current profile `FACEFIT_EXPERIMENTAL_SCORE_V1` has:

- `status: EXPERIMENTAL`
- `productionApproved: false`
- `evidenceApprovalStatus: NOT_APPROVED`
- synthetic-only evidence ID `EVIDENCE_TEST_FIXTURE_ONLY`
- synthetic permitted session `SES_900001`; real-user scoring and public API remain disabled.

Engine mode `DISABLED` returns no score. `EXPERIMENTAL` needs explicit opt-in. `PRODUCTION` fails closed without approved profile/evidence/validation/hash requirements (`docs/experimental-scoring-engine.md:7-13`).

## Input and quality gates

Each metric input carries value, unit, axis, answer ID and quality data. Required quality checks may include minimum sample count, availability ratio, maximum missing ratio, answer duration, word count, voiced-frame ratio and timestamp validity. Failure returns `NOT_SCORABLE`, `score: null`; absent data is never converted to 0.

All V1 metric gates require availability >= 0.8, missing <= 0.2, duration >= 1,000 ms and valid timestamps. Vision metrics require at least 10 samples. Speech metrics additionally require at least 5 words.

## V1 metric rules (all 0–100, two decimal places)

| Axis / metric | Weight | Conversion |
| --- | ---: | --- |
| GAZE_HEAD / yaw absolute P95 degrees | 0.50 | Piecewise: 0°=100, 20°=60, 50°=0; clamp outside range. |
| GAZE_HEAD / pitch absolute P95 degrees | 0.50 | Bands: [0,10)=100; [10,25]=60; (25,100]=0. |
| POSTURE / shoulder-tilt absolute P95 degrees | 0.60 | Piecewise: 0°=100, 5°=50, 10°=0; outside range unscorable. |
| POSTURE / shoulder-center velocity P95 normalized/sec | 0.40 | Piecewise: 0=100, .5=50, 1=0; clamp outside range. |
| SPEECH_DELIVERY / words per minute | 0.75 | Piecewise: 40=0, 100=100, 160=100, 220=0; outside range unscorable. |
| SPEECH_DELIVERY / filler candidates per minute | 0.25 | Bands: [0,1]=100; [2,10]=40; gaps/outside unscorable. |

Sources: `fixtures/profiles/experimental-scoring-profile-v1.json:8-74` and `engine/metric_scorer.py:37-96`.

`PIECEWISE_LINEAR` linearly interpolates between listed anchors. `BAND_LOOKUP` follows each explicit inclusive/exclusive bound. Decimal math is used, with `ROUND_HALF_UP` only at profile output precision.

## Aggregation

Metric score exists only when metric identity, axis, unit, quality gate and range pass.

```text
axisScore = sum(metricScore * metricWeight) / sum(included metricWeight)
```

Each axis needs coverage >= 0.5. Available weights are renormalized; partial axis score is allowed. POSTURE specifically requires shoulder-tilt metric. Missing required metric or insufficient coverage makes axis `NOT_SCORABLE` (`axis_aggregator.py:11-43`).

Answer overall score is disabled: `answerAggregation.overallEnabled: false`. Session rule is duration-weighted, needs at least 2 scorable answers and 50% answer coverage, and allows a partial session score. An overall cross-axis score is also disabled (`profile:71-73`).

If an enabled overall were configured, answer/session aggregation uses profile-selected weights only; no automatic equalization or imputation occurs (`answer_aggregator.py:11-39`, `session_aggregator.py:11-35`).

## Interpretation

These thresholds exercise code paths only. They are not valid production targets. In particular, “gaze” metrics use head-pose proxies, filler items are candidates requiring review, and 2D posture velocity depends on camera framing.
