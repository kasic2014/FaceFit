package com.facefit.backend.document.application;

public record ValidatedDocumentFile(
        String originalFileName,
        String extension,
        String mimeType,
        byte[] content
) {
    public long size() {
        return content.length;
    }
}
