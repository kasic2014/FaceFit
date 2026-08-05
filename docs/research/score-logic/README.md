# FaceFit score logic audit

## Scope and evidence

- Audited source: [kasic2014/FaceFit](https://github.com/kasic2014/FaceFit), commit `727a86a543218fb7fc3c3f46bfed8e8367020c08` (2026-08-05 KST).
- Checked: public/internal API routes, CV scorer, report aggregation, `ai-server/scoring` engine, Vision data-quality score, fixtures, and validation scripts.
- This folder records source behaviour; it does not copy or enable external scoring code in this project.

## Conclusion

There are three different values called “score.” They must not be conflated.

| Kind | Current state | Meaning |
| --- | --- | --- |
| CV `gazeScore`, `postureScore` | Calculated by `/internal/v1/analyses/cv` | 0–100 coaching proxies from video landmarks/frame motion. |
| `ai-server/scoring` | `EXPERIMENTAL`, synthetic-session only | Profile-driven metric/axis/session calculator. No real-user API or report use. |
| Vision `quality_score` / tracker score | Calculated internally | Capture/data integrity and target selection; never user evaluation. |

Backend report code additionally averages per-answer axis scores and axis averages, but current Analysis API exposes only CV scores. Voice and content endpoints return `503`; end-to-end report generation requiring all axes cannot complete against this API revision.

Read next:

- [active-pipeline.md](active-pipeline.md): active CV formulas, input gates, report aggregation, integration mismatch.
- [experimental-engine.md](experimental-engine.md): profile thresholds, weighting, quality gates, output statuses.
- [non-evaluation-scores.md](non-evaluation-scores.md): values that look like scores but are not interview scores.

## Verified commands

Ran against audited checkout:

```powershell
python ai-server\scoring\scripts\validate_scoring_package.py
python ai-server\scoring\scripts\run_experimental_scoring.py `
  --profile ai-server\scoring\fixtures\profiles\experimental-scoring-profile-v1.json `
  --input ai-server\scoring\fixtures\inputs\synthetic-scoring-input-v1.json `
  --allow-experimental
```

Results: `experimental_scoring_engine_ready`, `metricCount: 18`.

## Important limits

- Head pose proxy is not eye tracking/eye contact measurement.
- Shoulder/body metrics are 2D image-coordinate proxies; framing, camera position, and movement affect them.
- Thresholds in experimental profile explicitly use synthetic fixture evidence and are not approved production thresholds.
- No code reviewed establishes validity for hiring outcome, job fit, personality, emotion, confidence, or health.
