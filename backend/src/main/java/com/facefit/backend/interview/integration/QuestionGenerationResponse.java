package com.facefit.backend.interview.integration;

import com.facefit.backend.interview.domain.InterviewQuestionType;

import java.util.List;
import java.util.UUID;

public record QuestionGenerationResponse(
        String schemaVersion,
        UUID generationRequestId,
        List<GeneratedQuestion> questions
) {

    public record GeneratedQuestion(
            int order,
            InterviewQuestionType type,
            String category,
            String text
    ) {
    }
}
