package com.facefit.backend.interview.integration;

import com.facefit.backend.interview.domain.StorageProvider;

import java.util.UUID;

public record AnswerAnalysisRequest(
        UUID answerId,
        UUID sessionId,
        UUID questionId,
        String questionText,
        StorageProvider storageProvider,
        String storageBucket,
        String storageObjectKey,
        String mimeType,
        long mediaSizeBytes,
        int recordedDurationSeconds,
        long detectedDurationMillis,
        String transcript
) {
}
