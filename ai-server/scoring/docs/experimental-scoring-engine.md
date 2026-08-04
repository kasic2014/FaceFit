# Experimental scoring engine

Profiles externalize version, mode/approval state, score scale, metric rules, axis rules, answer/session aggregation, overall policy, and evidence references. Canonical UTF-8 JSON with sorted compact keys, excluding the `profileHash` field itself, produces the SHA-256 profile hash.

`PIECEWISE_LINEAR` interpolates Decimal values between sorted unique anchors. Values outside anchors clamp only when `clampOutsideRange=true`; otherwise they are not scorable. `BAND_LOOKUP` uses explicit inclusive/exclusive boundaries, rejects overlaps, and returns not scorable for unmatched values. Final values use `ROUND_HALF_UP` at profile precision.

Modes:

- `DISABLED` returns `scoringAvailable=false`, `scoreStatus=NOT_AVAILABLE`, and `score=null`.
- `EXPERIMENTAL` requires an `EXPERIMENTAL`, non-production profile and explicit `--allow-experimental`. It is fixture/research only and is not exposed through public APIs or stored in user reports.
- `PRODUCTION` fails closed with `SCORING_PROFILE_NOT_APPROVED` unless profile status, production/evidence/validation approvals, approver/time, declared verified hash, and approved evidence for every metric are all present.

The CLI accepts only profile, input, output root, explicit experimental opt-in, and validate-only. It accepts no participant/media/transcript paths or production enable switch. Atomic strict JSON rejects non-finite values, absolute paths, transcripts, participant identifiers, sensitive attributes, and psychological/hiring fields.
