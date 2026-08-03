package com.facefit.backend.interview.api;

import com.facefit.backend.interview.domain.InterviewCompletionType;
import com.facefit.backend.interview.domain.InterviewSessionStatus;

import java.time.OffsetDateTime;
import java.util.UUID;

public record InterviewCompletionResponse(
        UUID sessionId,
        InterviewSessionStatus sessionStatus,
        InterviewCompletionType completionType,
        OffsetDateTime endedAt
) {
}
