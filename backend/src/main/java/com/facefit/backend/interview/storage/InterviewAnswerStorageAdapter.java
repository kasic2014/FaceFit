package com.facefit.backend.interview.storage;

import com.facefit.backend.interview.domain.StorageProvider;

import java.net.URI;
import java.nio.file.Path;

interface InterviewAnswerStorageAdapter {

    StorageProvider provider();

    void upload(
            String bucket,
            String objectKey,
            String mimeType,
            long contentLength,
            String sha256,
            Path content
    );

    URI canonicalUrl(String bucket, String objectKey);

    URI createPresignedGetUrl(String bucket, String objectKey);

    void delete(String bucket, String objectKey);
}
