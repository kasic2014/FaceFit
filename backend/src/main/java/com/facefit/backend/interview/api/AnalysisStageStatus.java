package com.facefit.backend.interview.api;

public record AnalysisStageStatus(
        int total,
        int queued,
        int processing,
        int succeeded,
        int failed
) {
}
