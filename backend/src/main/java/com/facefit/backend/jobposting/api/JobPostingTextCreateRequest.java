package com.facefit.backend.jobposting.api;

public record JobPostingTextCreateRequest(
        String inputType,
        String rawText
) {
}
