package com.facefit.backend.interview.api;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.facefit.backend.interview.domain.InterviewSessionStatus;

import java.util.UUID;

public record InterviewAnalysisStatusResponse(
        UUID sessionId,
        InterviewSessionStatus sessionStatus,
        AnalysisStatus analysisStatus,
        int totalAnswerCount,
        int completedAnswerCount,
        int failedAnswerCount,
        int progressPercent,
        AnalysisStages stages,
        String reportStatus,
        boolean retryable,
        @JsonInclude(JsonInclude.Include.NON_NULL)
        String errorCode
) {
}
