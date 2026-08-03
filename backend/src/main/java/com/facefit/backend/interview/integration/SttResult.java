package com.facefit.backend.interview.integration;

public record SttResult(
        String schemaVersion,
        String transcript,
        String modelVersion,
        String language,
        double durationSec
) {

    public SttResult(String schemaVersion, String transcript) {
        this(schemaVersion, transcript, null, "ko", 0.0);
    }

    public SttResult(String transcript) {
        this("1.0", transcript);
    }
}
