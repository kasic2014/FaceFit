package com.facefit.backend.interview.api;

import com.facefit.backend.interview.domain.InterviewAnswerStatus;

import java.util.UUID;

public record InterviewAnswerCreatedResponse(
        UUID answerId,
        UUID questionId,
        InterviewAnswerStatus answerStatus,
        String nextQuestionStatus
) {
}
