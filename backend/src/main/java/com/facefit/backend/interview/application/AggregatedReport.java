package com.facefit.backend.interview.application;

import com.fasterxml.jackson.databind.JsonNode;

import java.math.BigDecimal;

public record AggregatedReport(
        String schemaVersion,
        String inputHash,
        BigDecimal overallScore,
        BigDecimal gazeScore,
        BigDecimal postureScore,
        BigDecimal speechScore,
        BigDecimal contentScore,
        JsonNode strengths,
        JsonNode improvements,
        JsonNode questionFeedback
) {
}
