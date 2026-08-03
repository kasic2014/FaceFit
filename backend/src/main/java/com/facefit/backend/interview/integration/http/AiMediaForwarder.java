package com.facefit.backend.interview.integration.http;

import com.facefit.backend.common.exception.StorageOperationException;
import com.facefit.backend.interview.integration.AnswerAnalysisRequest;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.storage.InterviewAnswerStorage;
import com.facefit.backend.interview.storage.StoredAnswerMedia;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.InputStream;
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
            Function<InputStream, PortResult<T>> operation
    ) {
        if (request == null
                || request.storageBucket() == null
                || request.storageBucket().isBlank()
                || request.storageObjectKey() == null
                || request.storageObjectKey().isBlank()) {
            return PortResult.permanentFailure("ANSWER_MEDIA_REFERENCE_INVALID");
        }
        try (StoredAnswerMedia media = storage.read(
                request.storageBucket(),
                request.storageObjectKey()
        )) {
            if (media.contentLength() > MAX_MEDIA_BYTES) {
                return PortResult.permanentFailure("PAYLOAD_TOO_LARGE");
            }
            return operation.apply(media.inputStream());
        } catch (StorageOperationException exception) {
            return "SUPABASE_STORAGE_NOT_CONFIGURED".equals(
                    exception.getMessage()
            )
                    ? PortResult.permanentFailure(
                    "ANSWER_STORAGE_NOT_CONFIGURED"
            )
                    : PortResult.retryableFailure("ANSWER_MEDIA_READ_FAILED");
        } catch (IOException exception) {
            return PortResult.retryableFailure("ANSWER_MEDIA_CLOSE_FAILED");
        } catch (RuntimeException exception) {
            return PortResult.permanentFailure("ANSWER_MEDIA_FORWARD_FAILED");
        }
    }
}
