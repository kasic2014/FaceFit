package com.facefit.backend.interview.api;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewSessionStatus;

import java.util.UUID;

public record CurrentQuestionResponse(
        UUID sessionId,
        InterviewSessionStatus sessionStatus,
        InterviewJobStatus questionGenerationStatus,
        CurrentQuestion currentQuestion,
        @JsonInclude(JsonInclude.Include.NON_NULL)
        String progressStatus,
        boolean canAnswer,
        boolean canFinish
) {
}
