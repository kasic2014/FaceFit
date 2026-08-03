package com.facefit.backend.interview.api;

import com.facefit.backend.interview.domain.InterviewQuestionType;

import java.util.UUID;

public record CurrentQuestion(
        UUID questionId,
        int order,
        InterviewQuestionType type,
        String category,
        String text
) {
}
