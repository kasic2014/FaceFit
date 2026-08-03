package com.facefit.backend.interview.api;

import com.fasterxml.jackson.databind.JsonNode;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.UUID;

public record InterviewReportData(
        UUID reportId,
        String schemaVersion,
        BigDecimal overallScore,
        ReportScores scores,
        JsonNode strengths,
        JsonNode improvements,
        JsonNode questionFeedback,
        OffsetDateTime generatedAt
) {

    public record ReportScores(
            BigDecimal gaze,
            BigDecimal posture,
            BigDecimal speech,
            BigDecimal content
    ) {
    }
}
