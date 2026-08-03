package com.facefit.backend.interview.storage;

public interface InterviewAnswerStorage {

    void upload(String bucket, String objectKey, String mimeType, byte[] content);

    StoredAnswerMedia read(String bucket, String objectKey);

    void delete(String bucket, String objectKey);
}
