# Scoring policy V1

Every measurement is converted to the common Metric Input contract before calculation. A profile must identify registered metrics, exact units, weights, quality gates, score functions, and evidence IDs. The engine never infers direction or boundaries.

Quality gates can require sample count, availability, missing ratio, answer duration, word count, voiced-frame ratio, and timestamp validity. Failure yields `NOT_SCORABLE` and `score=null`; missing detection, pitch, timestamps, or words never become zero or an automatic penalty.

Metric scoring supports `PIECEWISE_LINEAR` anchors and explicit `BAND_LOOKUP` boundaries. Decimal arithmetic uses `Decimal(str(value))`, sufficient intermediate precision, and `ROUND_HALF_UP` only at the profile-defined output precision. Clamping occurs only when the profile says so.

Axis coverage is scorable weight divided by total configured weight. Missing-weight renormalization and partial results require explicit axis policy. Required metric absence or insufficient coverage produces `NOT_SCORABLE`. Answer overall scores require explicit activation and are off in the experimental default. Session aggregation is selected by profile from `EQUAL`, `DURATION_WEIGHTED`, or `VALID_SAMPLE_WEIGHTED`; no method is inferred. Overall score is off by default.
