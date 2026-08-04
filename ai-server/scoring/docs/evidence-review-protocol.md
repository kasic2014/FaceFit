# Evidence review protocol

For each source record title, authors, year, DOI and official URL, file SHA-256, exact metric definition and unit, whether a threshold is actually stated, and exact page/table/figure location. If a threshold is not stated, store `null`; do not derive one silently.

Mapping relations are `DIRECT`, `PROXY`, `UNIT_CONVERSION`, `DERIVED`, and `NOT_APPLICABLE`. A proxy must never be presented as direct evidence. Head Pose yaw is not eye-contact ratio; pitch variation is not confidence; filler candidates are not overall communication ability; shoulder motion is not personality or attitude. Record population, language, interview context, capture setup, conversion formula, limitations, conflicting results, reviewer, and approval state.

Private/paid PDFs remain outside Git. Git may contain redistributable metadata, hashes, locations, mappings, and limitations only. Production approval requires reviewed evidence for every scoring metric.
