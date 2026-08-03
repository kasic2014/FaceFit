package com.facefit.backend.interview.api;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.facefit.backend.interview.domain.InterviewAnswerStatus;
import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewJobType;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public record InterviewAnswerResponse(
        UUID answerId,
        UUID sessionId,
        UUID questionId,
        InterviewAnswerStatus status,
        boolean nextQuestionReady,
        @JsonInclude(JsonInclude.Include.NON_NULL)
        UUID nextQuestionId,
        List<ProcessingStep> processingSteps,
        OffsetDateTime createdAt,
        OffsetDateTime confirmedAt
) {

    public record ProcessingStep(
            InterviewJobType type,
            InterviewJobStatus status,
            int attemptCount,
            int maxAttempts,
            @JsonInclude(JsonInclude.Include.NON_NULL)
            String failureCode
    ) {
    }
}
