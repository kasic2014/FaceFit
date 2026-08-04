package com.facefit.backend.interview.storage;

import com.facefit.backend.interview.domain.StorageProvider;

import java.net.URI;
import java.nio.file.Path;

public interface InterviewAnswerStorage {

    void upload(
            StorageProvider provider,
            String bucket,
            String objectKey,
            String mimeType,
            long contentLength,
            String sha256,
            Path content
    );

    URI canonicalUrl(StorageProvider provider, String bucket, String objectKey);

    URI createPresignedGetUrl(
            StorageProvider provider,
            String bucket,
            String objectKey
    );

    void delete(StorageProvider provider, String bucket, String objectKey);
}
