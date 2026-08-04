package com.facefit.backend.interview.storage;

import com.facefit.backend.common.exception.StorageOperationException;
import com.facefit.backend.interview.domain.StorageProvider;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.nio.file.Path;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

@Component
public class RoutingInterviewAnswerStorage implements InterviewAnswerStorage {

    private final Map<StorageProvider, InterviewAnswerStorageAdapter> adapters;

    RoutingInterviewAnswerStorage(List<InterviewAnswerStorageAdapter> adapters) {
        EnumMap<StorageProvider, InterviewAnswerStorageAdapter> indexed =
                new EnumMap<>(StorageProvider.class);
        adapters.forEach(adapter -> indexed.put(adapter.provider(), adapter));
        this.adapters = Map.copyOf(indexed);
    }

    @Override
    public void upload(StorageProvider provider, String bucket, String objectKey,
                       String mimeType, long contentLength, String sha256, Path content) {
        adapter(provider).upload(bucket, objectKey, mimeType, contentLength, sha256, content);
    }

    @Override
    public URI canonicalUrl(StorageProvider provider, String bucket, String objectKey) {
        return adapter(provider).canonicalUrl(bucket, objectKey);
    }

    @Override
    public URI createPresignedGetUrl(StorageProvider provider, String bucket, String objectKey) {
        return adapter(provider).createPresignedGetUrl(bucket, objectKey);
    }

    @Override
    public void delete(StorageProvider provider, String bucket, String objectKey) {
        adapter(provider).delete(bucket, objectKey);
    }

    private InterviewAnswerStorageAdapter adapter(StorageProvider provider) {
        InterviewAnswerStorageAdapter adapter = provider == null ? null : adapters.get(provider);
        if (adapter == null) {
            throw new StorageOperationException("ANSWER_STORAGE_PROVIDER_UNSUPPORTED");
        }
        return adapter;
    }
}
