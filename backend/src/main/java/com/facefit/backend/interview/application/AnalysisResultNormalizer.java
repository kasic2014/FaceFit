package com.facefit.backend.interview.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.integration.AnalysisResult;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;

@Component
@RequiredArgsConstructor
public class AnalysisResultNormalizer {

    private static final int MAX_FEEDBACK_ITEMS = 5;
    private static final int MAX_FEEDBACK_LENGTH = 500;

    private final ObjectMapper objectMapper;

    public NormalizedAnalysisResult normalize(
            InterviewJobType type,
            AnalysisResult result
    ) {
        if (result == null || result.payload() == null || !result.payload().isObject()) {
            return null;
        }
        JsonNode payload = result.payload();
        String schemaVersion = text(payload, "schemaVersion", 20);
        if (schemaVersion == null) {
            return null;
        }
        ArrayNode feedback = normalizeFeedback(payload.path("feedback"));
        if (feedback == null) {
            return null;
        }
        return switch (type) {
            case CV -> {
                BigDecimal gaze = score(payload, "gazeScore");
                BigDecimal posture = score(payload, "postureScore");
                yield gaze == null || posture == null
                        ? null
                        : new NormalizedAnalysisResult(
                                schemaVersion,
                                gaze,
                                posture,
                                null,
                                null,
                                feedback
                        );
            }
            case VOICE -> {
                BigDecimal speech = score(payload, "speechScore");
                yield speech == null
                        ? null
                        : new NormalizedAnalysisResult(
                                schemaVersion,
                                null,
                                null,
                                speech,
                                null,
                                feedback
                        );
            }
            case CONTENT -> {
                BigDecimal content = score(payload, "contentScore");
                yield content == null
                        ? null
                        : new NormalizedAnalysisResult(
                                schemaVersion,
                                null,
                                null,
                                null,
                                content,
                                feedback
                        );
            }
            default -> null;
        };
    }

    private BigDecimal score(JsonNode payload, String field) {
        JsonNode value = payload.get(field);
        if (value == null || !value.isNumber()) {
            return null;
        }
        BigDecimal score = value.decimalValue();
        if (score.compareTo(BigDecimal.ZERO) < 0
                || score.compareTo(BigDecimal.valueOf(100)) > 0) {
            return null;
        }
        return score.setScale(1, RoundingMode.HALF_UP);
    }

    private ArrayNode normalizeFeedback(JsonNode value) {
        ArrayNode normalized = objectMapper.createArrayNode();
        if (value.isMissingNode() || value.isNull()) {
            return normalized;
        }
        if (!value.isArray() || value.size() > MAX_FEEDBACK_ITEMS) {
            return null;
        }
        for (JsonNode item : value) {
            if (!item.isTextual()) {
                return null;
            }
            String text = item.textValue().strip();
            if (text.isBlank()
                    || text.codePointCount(0, text.length()) > MAX_FEEDBACK_LENGTH) {
                return null;
            }
            normalized.add(text);
        }
        return normalized;
    }

    private String text(JsonNode payload, String field, int maxLength) {
        JsonNode value = payload.get(field);
        if (value == null || !value.isTextual()) {
            return null;
        }
        String text = value.textValue().strip();
        if (text.isBlank() || text.length() > maxLength) {
            return null;
        }
        return text;
    }
}
