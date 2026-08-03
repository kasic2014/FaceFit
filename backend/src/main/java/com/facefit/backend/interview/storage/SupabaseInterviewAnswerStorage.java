package com.facefit.backend.interview.storage;

import com.facefit.backend.common.exception.StorageOperationException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.stream.Collectors;

@Component
public class SupabaseInterviewAnswerStorage implements InterviewAnswerStorage {

    private final String projectUrl;
    private final String secretKey;
    private final HttpClient httpClient;

    @Autowired
    public SupabaseInterviewAnswerStorage(
            @Value("${facefit.storage.supabase.project-url:}") String projectUrl,
            @Value("${facefit.storage.supabase.secret-key:}") String secretKey
    ) {
        this(projectUrl, secretKey, HttpClient.newHttpClient());
    }

    SupabaseInterviewAnswerStorage(
            String projectUrl,
            String secretKey,
            HttpClient httpClient
    ) {
        this.projectUrl = stripTrailingSlash(projectUrl);
        this.secretKey = secretKey == null ? "" : secretKey;
        this.httpClient = httpClient;
    }

    @Override
    public void upload(String bucket, String objectKey, String mimeType, byte[] content) {
        requireConfigured();
        HttpRequest request = authorizedRequest(objectUri(bucket, objectKey))
                .header("Content-Type", mimeType)
                .header("x-upsert", "false")
                .POST(HttpRequest.BodyPublishers.ofByteArray(content))
                .build();
        send(request, "ANSWER_STORAGE_UPLOAD_FAILED");
    }

    @Override
    public StoredAnswerMedia read(String bucket, String objectKey) {
        requireConfigured();
        HttpRequest request = authorizedRequest(objectUri(bucket, objectKey))
                .GET()
                .build();
        try {
            HttpResponse<java.io.InputStream> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofInputStream()
            );
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                response.body().close();
                throw new StorageOperationException("ANSWER_STORAGE_READ_FAILED");
            }
            long contentLength = response.headers()
                    .firstValueAsLong("Content-Length")
                    .orElse(-1);
            return new StoredAnswerMedia(response.body(), contentLength);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new StorageOperationException(
                    "ANSWER_STORAGE_READ_INTERRUPTED",
                    exception
            );
        } catch (IOException exception) {
            throw new StorageOperationException("ANSWER_STORAGE_READ_FAILED", exception);
        }
    }

    @Override
    public void delete(String bucket, String objectKey) {
        requireConfigured();
        String escaped = objectKey
                .replace("\\", "\\\\")
                .replace("\"", "\\\"");
        HttpRequest request = authorizedRequest(bucketUri(bucket))
                .header("Content-Type", "application/json")
                .method(
                        "DELETE",
                        HttpRequest.BodyPublishers.ofString(
                                "{\"prefixes\":[\"" + escaped + "\"]}"
                        )
                )
                .build();
        send(request, "ANSWER_STORAGE_DELETE_FAILED");
    }

    private void send(HttpRequest request, String errorCode) {
        try {
            HttpResponse<Void> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.discarding()
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
        return URI.create(
                projectUrl
                        + "/storage/v1/object/"
                        + encodeSegment(bucket)
                        + "/"
                        + Arrays.stream(objectKey.split("/"))
                        .map(SupabaseInterviewAnswerStorage::encodeSegment)
                        .collect(Collectors.joining("/"))
        );
    }

    private URI bucketUri(String bucket) {
        return URI.create(projectUrl + "/storage/v1/object/" + encodeSegment(bucket));
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
