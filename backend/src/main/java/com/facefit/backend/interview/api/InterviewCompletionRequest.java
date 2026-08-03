package com.facefit.backend.interview.api;

import com.facefit.backend.interview.domain.InterviewCompletionType;

public record InterviewCompletionRequest(
        InterviewCompletionType completionType
) {
}
