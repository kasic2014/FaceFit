package com.facefit.backend.document.storage;

public interface CareerDocumentStorage {

    void upload(String bucket, String objectKey, String mimeType, byte[] content);

    void delete(String bucket, String objectKey);
}
