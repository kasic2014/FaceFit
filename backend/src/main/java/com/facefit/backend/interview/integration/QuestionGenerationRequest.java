package com.facefit.backend.interview.integration;

import com.facefit.backend.interview.domain.JobPostingSnapshot;

import java.util.UUID;

public record QuestionGenerationRequest(
        String schemaVersion,
        UUID generationRequestId,
        String locale,
        String persona,
        String difficulty,
        QuestionPolicy questionPolicy,
        DocumentText resume,
        DocumentText coverLetter,
        JobPostingSnapshot jobPostingSnapshot
) {

    public record QuestionPolicy(
            int totalCount,
            boolean allowFollowUpQuestion
    ) {
    }

    public record DocumentText(String text) {
    }
}
