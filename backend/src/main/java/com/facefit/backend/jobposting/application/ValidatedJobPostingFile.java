package com.facefit.backend.jobposting.application;

public record ValidatedJobPostingFile(
        String originalFileName,
        String extension,
        String mimeType,
        JobPostingFileFormat format,
        byte[] content
) {
    public long size() {
        return content.length;
    }
}
