package com.facefit.backend.interview.application;

public record ValidatedAnswerMedia(
        byte[] content,
        String mimeType,
        String extension,
        long size,
        String sha256,
        long durationMillis
) {
}
