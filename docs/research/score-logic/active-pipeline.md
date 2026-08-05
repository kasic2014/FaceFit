# Active API and report pipeline

## 1. CV endpoint

`ai-server/analysis-server/app/api/analyses.py:119-153` exposes `POST /internal/v1/analyses/cv`. It downloads one answer video, runs `cv_analyzer.analyze`, then returns `gazeScore` and `postureScore` in 0–100 range.

`/voice` and `/content` deliberately respond `503` (`analyses.py:156-189`). Therefore current API has no operational `speechScore` or `contentScore` calculation.

## 2. Frame eligibility

`score_observations` in `app/services/cv_analyzer.py:300-336` rejects video unless all conditions hold:

- at least configured `min_usable_frames` total frames;
- no frame contains more than one face;
- at least that many frames contain exactly one face and face area;
- no more than half sized faces lie outside `MIN_FACE_AREA..MAX_FACE_AREA`;
- usable frames are in face-area range and contain finite: face center X/Y, yaw proxy, pitch proxy, roll degrees, shoulder tilt, shoulder center X/Y, head–shoulder offset;
- usable frames are at least `min_usable_frames` and at least half of all frames.

Failed gate raises `AnalyzerMediaFailure`; it returns no partial score.

## 3. Shared normalizer

For any non-negative deviation `x`, with good boundary `g`, bad boundary `b` (`cv_analyzer.py:290-297`):

```text
Q(x; g, b) = 100                  if x <= g
             0                    if x >= b
             100 * (b - x)/(b-g) otherwise
```

Inputs are always deviations or magnitudes, so lower means closer to preferred camera-facing/stable geometry. Non-finite input maps to 0, but required fields have already been rejected as non-finite.

## 4. `gazeScore` formula

Per usable frame:

```text
facing = [Q(yaw_proxy, 0.04, 0.22)
        + Q(pitch_proxy, 0.04, 0.20)
        + Q(abs roll degrees, 5, 25)] / 3
```

The source applies `Q(roll_degrees, 5, 25)` directly; correct behaviour assumes `roll_degrees` already represents absolute magnitude. Frame-to-frame face-center displacement is Euclidean distance, then:

```text
face_stability = Q(mean(displacement), 0.01, 0.08)
gazeScore = 0.85 * mean(facing) + 0.15 * face_stability
```

Finally clamp to 0–100 and round one decimal (`cv_analyzer.py:338-356, 383-386`). This is head direction + head stability, not gaze/iris tracking.

## 5. `postureScore` formula

All per-frame components are averaged first:

```text
tilt      = mean(Q(shoulder_tilt_degrees, 3, 18))
center    = mean(Q(abs(shoulder_center_x - 0.5), 0.05, 0.25))
alignment = mean(Q(head_shoulder_offset, 0.08, 0.35))
movement  = Q(mean(shoulder-center frame displacement), 0.01, 0.10)

postureScore = 0.35*tilt + 0.25*center + 0.20*alignment + 0.20*movement
```

Final clamp/round matches `gazeScore` (`cv_analyzer.py:358-386`). It measures screen-position alignment and movement proxies, not clinical posture or body quality.

## 6. Backend report arithmetic

`backend/.../InterviewReportAggregator.java:32-184` expects 10 answers and, when voice analysis enabled, exactly 30 analysis results (CV, VOICE, CONTENT each answer). For each axis it:

1. collects each answer score;
2. averages answer scores with `HALF_UP` to one decimal;
3. averages available axis averages equally, again `HALF_UP` to one decimal, as `overallScore`.

With voice disabled it expects 20 results and excludes only SPEECH. It does **not** weight questions or axes differently.

## 7. Integration findings

- `AnalysisResultNormalizer.java:40-94` accepts numeric 0–100 values and rounds one decimal.
- It also requires `schemaVersion` (`:31-34`), while current CV API response construction (`analyses.py:146-153`) does not add that field. This source revision has an API/consumer contract mismatch.
- Current CV endpoint can calculate its two fields. Current voice/content endpoints cannot produce fields required by report aggregation. Treat full report score as unavailable unless deployed components use a different compatible version.
