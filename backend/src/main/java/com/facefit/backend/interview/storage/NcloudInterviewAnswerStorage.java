package com.facefit.backend.interview.storage;

import com.facefit.backend.common.exception.StorageOperationException;
import com.facefit.backend.interview.domain.StorageProvider;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Arrays;
import java.util.Map;
import java.util.stream.Collectors;

@Component
public class NcloudInterviewAnswerStorage implements InterviewAnswerStorageAdapter {

    private final NcloudObjectStorageProperties ncloud;
    private final InterviewAnswerStorageProperties answers;
    private final S3Client s3Client;
    private final S3Presigner presigner;

    public NcloudInterviewAnswerStorage(
            NcloudObjectStorageProperties ncloud,
            InterviewAnswerStorageProperties answers,
            S3Client s3Client,
            S3Presigner presigner
    ) {
        this.ncloud = ncloud;
        this.answers = answers;
        this.s3Client = s3Client;
        this.presigner = presigner;
    }

    @Override
    public StorageProvider provider() {
        return StorageProvider.NCLOUD;
    }

    @Override
    public void upload(String bucket, String objectKey, String mimeType,
                       long contentLength, String sha256, Path content) {
        requireConfigured();
        try {
            String extension = objectKey.substring(objectKey.lastIndexOf('.') + 1);
            PutObjectRequest request = PutObjectRequest.builder()
                    .bucket(bucket)
                    .key(objectKey)
                    .contentType(mimeType)
                    .contentLength(contentLength)
                    .metadata(Map.of("sha256", sha256, "extension", extension))
                    .build();
            s3Client.putObject(request, RequestBody.fromFile(content));
        } catch (RuntimeException exception) {
            throw new StorageOperationException("ANSWER_STORAGE_UPLOAD_FAILED", exception);
        }
    }

    @Override
    public URI canonicalUrl(String bucket, String objectKey) {
        URI endpoint = ncloud.getEndpoint();
        if (!"https".equalsIgnoreCase(endpoint.getScheme()) || endpoint.getQuery() != null) {
            throw new StorageOperationException("NCLOUD_STORAGE_ENDPOINT_INVALID");
        }
        String base = endpoint.toString().replaceFirst("/+$", "");
        return URI.create(base + "/" + encode(bucket) + "/" + encodeKey(objectKey));
    }

    @Override
    public URI createPresignedGetUrl(String bucket, String objectKey) {
        requireConfigured();
        int ttl = answers.getPresignedGetTtlSeconds();
        if (ttl < 121 || ttl > 3600) {
            throw new StorageOperationException("ANSWER_PRESIGN_TTL_INVALID");
        }
        try {
            GetObjectRequest objectRequest = GetObjectRequest.builder()
                    .bucket(bucket)
                    .key(objectKey)
                    .build();
            return presigner.presignGetObject(GetObjectPresignRequest.builder()
                            .signatureDuration(Duration.ofSeconds(ttl))
                            .getObjectRequest(objectRequest)
                            .build())
                    .url().toURI();
        } catch (Exception exception) {
            throw new StorageOperationException("ANSWER_PRESIGN_FAILED", exception);
        }
    }

    @Override
    public void delete(String bucket, String objectKey) {
        requireConfigured();
        try {
            s3Client.deleteObject(DeleteObjectRequest.builder()
                    .bucket(bucket).key(objectKey).build());
        } catch (RuntimeException exception) {
            throw new StorageOperationException("ANSWER_STORAGE_DELETE_FAILED", exception);
        }
    }

    private void requireConfigured() {
        if (!ncloud.configured()) {
            throw new StorageOperationException("NCLOUD_STORAGE_NOT_CONFIGURED");
        }
    }

    private static String encodeKey(String key) {
        return Arrays.stream(key.split("/"))
                .map(NcloudInterviewAnswerStorage::encode)
                .collect(Collectors.joining("/"));
    }

    private static String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }
}
