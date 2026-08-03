package com.facefit.backend.interview.api;

import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewSessionStatus;

import java.util.UUID;

public record InterviewStartResponse(
        UUID sessionId,
        InterviewSessionStatus sessionStatus,
        InterviewJobStatus questionGenerationStatus,
        CurrentQuestion currentQuestion
) {
}
