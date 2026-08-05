# Non-evaluation score-like values

## Vision interval `quality_score`

`vision-server/app/vision/interval_feature_aggregator.py:557-634` calculates a 0–1 arithmetic mean of:

- head-pose availability ratio;
- shoulder/posture availability ratio;
- nose-alignment availability ratio;
- face-alignment availability ratio;
- target continuity;
- timestamp monotonicity (1 or 0);
- no duplicate timestamps/frames (1 or 0).

It is a data/capture integrity indicator. Structural failure occurs for no frames, target mismatch, duplicate/non-monotonic timestamps, duplicate frame index, insufficient availability, or no valid values. It is not user posture score.

## Session-neutral baseline `quality_score`

`neutral_baseline_estimator.py:277-387` returns 0–1 mean of target continuity, candidate coverage/retention, head/posture confidence, and motion stabilities. Baseline values use median with MAD outlier filtering. It declares collection quality, explicitly not neutral ground truth or interview evaluation.

## Target-tracker candidate cost

`single_target_tracker.py:34-48` ranks candidate faces with a lower-is-better internal cost:

```text
0.55*persistence + 0.30*center_distance
- 0.15*size_reward - 0.10*detection_confidence
```

It selects/tracks a single target and can emit ambiguity from score margin. It is not human performance scoring.

## Fixture-only Vision threshold result

`vision-server/app/vision/scoring_strategy.py` can output `SCORED_TEST_FIXTURE` with `test_fixture_score` only when a fixture threshold profile produces exactly one matching band. The source labels this value synthetic, with no production/user-evaluation use. Public vision feedback schema returns `scores: null` and `scoringAvailable: false`.
