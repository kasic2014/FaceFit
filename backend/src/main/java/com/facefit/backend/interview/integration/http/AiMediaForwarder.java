package com.facefit.backend.interview.integration.http;

import com.facefit.backend.common.exception.StorageOperationException;
import com.facefit.backend.interview.integration.AnswerAnalysisRequest;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.storage.InterviewAnswerStorage;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.util.function.Function;

@Component
final class AiMediaForwarder {

    private static final long MAX_MEDIA_BYTES = 200L * 1024 * 1024;

    private final InterviewAnswerStorage storage;

    AiMediaForwarder(InterviewAnswerStorage storage) {
        this.storage = storage;
    }

    <T> PortResult<T> forward(
            AnswerAnalysisRequest request,
            Function<URI, PortResult<T>> operation
    ) {
        if (request == null
                || request.storageProvider() == null
                || request.storageBucket() == null
                || request.storageBucket().isBlank()
                || request.storageObjectKey() == null
                || request.storageObjectKey().isBlank()
                || request.mediaSizeBytes() < 1
                || request.mediaSizeBytes() > MAX_MEDIA_BYTES) {
            return PortResult.permanentFailure("ANSWER_MEDIA_REFERENCE_INVALID");
        }
        try {
            URI presignedUrl = storage.createPresignedGetUrl(
                    request.storageProvider(),
                    request.storageBucket(),
                    request.storageObjectKey()
            );
            if (presignedUrl == null
                    || !"https".equalsIgnoreCase(presignedUrl.getScheme())
                    || presignedUrl.getRawQuery() == null) {
                return PortResult.permanentFailure("ANSWER_PRESIGNED_URL_INVALID");
            }
            return operation.apply(presignedUrl);
        } catch (StorageOperationException exception) {
            String code = exception.getMessage();
            if ("NCLOUD_STORAGE_NOT_CONFIGURED".equals(code)
                    || "SUPABASE_STORAGE_NOT_CONFIGURED".equals(code)
                    || "ANSWER_PRESIGN_TTL_INVALID".equals(code)) {
                return PortResult.permanentFailure("ANSWER_STORAGE_NOT_CONFIGURED");
            }
            return PortResult.retryableFailure("ANSWER_PRESIGN_FAILED");
        } catch (RuntimeException exception) {
            return PortResult.permanentFailure("ANSWER_MEDIA_FORWARD_FAILED");
        }
    }
}
