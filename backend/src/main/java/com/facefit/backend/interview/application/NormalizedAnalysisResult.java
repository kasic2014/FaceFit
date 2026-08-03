package com.facefit.backend.interview.application;

import com.fasterxml.jackson.databind.JsonNode;

import java.math.BigDecimal;

public record NormalizedAnalysisResult(
        String schemaVersion,
        BigDecimal gazeScore,
        BigDecimal postureScore,
        BigDecimal speechScore,
        BigDecimal contentScore,
        JsonNode publicFeedback
) {
}
