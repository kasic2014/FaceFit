package com.facefit.backend.interview.api;

import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;

import java.util.UUID;

public record InterviewSessionCreatedResponse(
        UUID sessionId,
        InterviewSessionStatus status
) {

    public static InterviewSessionCreatedResponse from(InterviewSession session) {
        return new InterviewSessionCreatedResponse(
                session.getSessionId(),
                session.getStatus()
        );
    }
}
