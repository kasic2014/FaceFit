package com.facefit.backend.interview.integration;

import java.util.UUID;

public record AnswerAnalysisRequest(
        UUID answerId,
        UUID sessionId,
        UUID questionId,
        String questionText,
        String storageBucket,
        String storageObjectKey,
        String mimeType,
        long detectedDurationMillis,
        String transcript
) {
}
