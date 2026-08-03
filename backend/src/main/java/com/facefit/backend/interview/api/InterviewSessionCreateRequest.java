package com.facefit.backend.interview.api;

import java.util.UUID;

public record InterviewSessionCreateRequest(
        UUID resumeDocumentId,
        UUID coverLetterDocumentId,
        UUID jobPostingId,
        String persona,
        String difficulty
) {
}
