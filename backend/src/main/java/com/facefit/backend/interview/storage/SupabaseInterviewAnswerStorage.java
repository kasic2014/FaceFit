package com.facefit.backend.interview.storage;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.facefit.backend.common.exception.StorageOperationException;
import com.facefit.backend.interview.domain.StorageProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.stream.Collectors;

@Component
public class SupabaseInterviewAnswerStorage implements InterviewAnswerStorageAdapter {

    private final String projectUrl;
    private final String secretKey;
    private final int presignedTtlSeconds;
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;

    @Autowired
    public SupabaseInterviewAnswerStorage(
            @Value("${facefit.storage.supabase.project-url:}") String projectUrl,
            @Value("${facefit.storage.supabase.secret-key:}") String secretKey,
            @Value("${facefit.storage.interview-answers.presigned-get-ttl-seconds:300}")
            int presignedTtlSeconds,
            ObjectMapper objectMapper
    ) {
        this(projectUrl, secretKey, presignedTtlSeconds,
                HttpClient.newHttpClient(), objectMapper);
    }

    SupabaseInterviewAnswerStorage(
            String projectUrl,
            String secretKey,
            int presignedTtlSeconds,
            HttpClient httpClient,
            ObjectMapper objectMapper
    ) {
        this.projectUrl = stripTrailingSlash(projectUrl);
        this.secretKey = secretKey == null ? "" : secretKey;
        this.presignedTtlSeconds = presignedTtlSeconds;
        this.httpClient = httpClient;
        this.objectMapper = objectMapper;
    }

    @Override
    public StorageProvider provider() {
        return StorageProvider.SUPABASE;
    }

    @Override
    public void upload(String bucket, String objectKey, String mimeType,
                       long contentLength, String sha256, Path content) {
        requireConfigured();
        try {
            HttpRequest request = authorizedRequest(objectUri(bucket, objectKey))
                    .header("Content-Type", mimeType)
                    .header("Content-Length", Long.toString(contentLength))
                    .header("x-upsert", "false")
                    .POST(HttpRequest.BodyPublishers.ofFile(content))
                    .build();
            send(request, "ANSWER_STORAGE_UPLOAD_FAILED");
        } catch (IOException exception) {
            throw new StorageOperationException("ANSWER_STORAGE_UPLOAD_FAILED", exception);
        }
    }

    @Override
    public URI canonicalUrl(String bucket, String objectKey) {
        requireConfigured();
        return objectUri(bucket, objectKey);
    }

    @Override
    public URI createPresignedGetUrl(String bucket, String objectKey) {
        requireConfigured();
        HttpRequest request = authorizedRequest(signUri(bucket, objectKey))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(
                        "{\"expiresIn\":" + presignedTtlSeconds + "}"
                ))
                .build();
        try {
            HttpResponse<String> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofString()
            );
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new StorageOperationException("ANSWER_PRESIGN_FAILED");
            }
            JsonNode payload = objectMapper.readTree(response.body());
            String signedUrl = payload.path("signedURL").asText("");
            if (signedUrl.isBlank()) {
                throw new StorageOperationException("ANSWER_PRESIGN_FAILED");
            }
            URI result = URI.create(signedUrl);
            return result.isAbsolute() ? result : URI.create(projectUrl + signedUrl);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new StorageOperationException("ANSWER_PRESIGN_INTERRUPTED", exception);
        } catch (IOException | IllegalArgumentException exception) {
            throw new StorageOperationException("ANSWER_PRESIGN_FAILED", exception);
        }
    }

    @Override
    public void delete(String bucket, String objectKey) {
        requireConfigured();
        String escaped = objectKey.replace("\\", "\\\\").replace("\"", "\\\"");
        HttpRequest request = authorizedRequest(bucketUri(bucket))
                .header("Content-Type", "application/json")
                .method("DELETE", HttpRequest.BodyPublishers.ofString(
                        "{\"prefixes\":[\"" + escaped + "\"]}"
                )).build();
        send(request, "ANSWER_STORAGE_DELETE_FAILED");
    }

    private void send(HttpRequest request, String errorCode) {
        try {
            HttpResponse<Void> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.discarding()
            );
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new StorageOperationException(errorCode);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new StorageOperationException(errorCode, exception);
        } catch (IOException exception) {
            throw new StorageOperationException(errorCode, exception);
        }
    }

    private HttpRequest.Builder authorizedRequest(URI uri) {
        return HttpRequest.newBuilder(uri)
                .header("Authorization", "Bearer " + secretKey)
                .header("apikey", secretKey);
    }

    private URI objectUri(String bucket, String objectKey) {
        return URI.create(projectUrl + "/storage/v1/object/" + encodeSegment(bucket)
                + "/" + encodedKey(objectKey));
    }

    private URI signUri(String bucket, String objectKey) {
        return URI.create(projectUrl + "/storage/v1/object/sign/"
                + encodeSegment(bucket) + "/" + encodedKey(objectKey));
    }

    private URI bucketUri(String bucket) {
        return URI.create(projectUrl + "/storage/v1/object/" + encodeSegment(bucket));
    }

    private String encodedKey(String objectKey) {
        return Arrays.stream(objectKey.split("/"))
                .map(SupabaseInterviewAnswerStorage::encodeSegment)
                .collect(Collectors.joining("/"));
    }

    private void requireConfigured() {
        if (projectUrl.isBlank() || secretKey.isBlank()) {
            throw new StorageOperationException("SUPABASE_STORAGE_NOT_CONFIGURED");
        }
    }

    private static String encodeSegment(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }

    private static String stripTrailingSlash(String value) {
        return value == null ? "" : value.replaceFirst("/+$", "");
    }
}
