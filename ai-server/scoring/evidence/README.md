# Evidence workspace

This directory contains redistributable paper metadata, review records, and Face-Fit mappings. It never contains paper files, participant media/data, transcripts, institutional tokens, or personal information.

- `source-catalog-v1.json` is the fixed Stage 31 catalog of 20 sources.
- `records/` contains one strict JSON record per source.
- `private/` is ignored and may contain locally reviewed paper files. A file hash may appear in a record, but a local path must not.

An algorithm error, association, model parameter, performance value, sample split, or descriptive statistic is not a Face-Fit behavior boundary. Evidence mappings do not activate the scoring engine or modify the metric registry.
