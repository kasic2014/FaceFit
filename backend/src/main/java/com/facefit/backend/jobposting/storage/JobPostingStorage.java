package com.facefit.backend.jobposting.storage;

public interface JobPostingStorage {

    void upload(String bucket, String objectKey, String mimeType, byte[] content);

    byte[] download(String bucket, String objectKey);

    void delete(String bucket, String objectKey);
}
