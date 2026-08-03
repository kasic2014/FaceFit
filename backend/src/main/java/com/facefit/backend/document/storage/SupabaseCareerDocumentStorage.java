package com.facefit.backend.document.storage;

import com.facefit.backend.common.exception.StorageOperationException;
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

@Component
public class SupabaseCareerDocumentStorage implements CareerDocumentStorage {

    private final String projectUrl;
    private final String secretKey;
    private final HttpClient httpClient;

    @Autowired
    public SupabaseCareerDocumentStorage(
            @Value("${facefit.storage.supabase.project-url:}") String projectUrl,
            @Value("${facefit.storage.supabase.secret-key:}") String secretKey
    ) {
        this(projectUrl, secretKey, HttpClient.newHttpClient());
    }

    SupabaseCareerDocumentStorage(
            String projectUrl,
            String secretKey,
            HttpClient httpClient
    ) {
        this.projectUrl = stripTrailingSlash(projectUrl);
        this.secretKey = secretKey;
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
        send(request, "Storage 업로드에 실패했습니다.");
    }

    @Override
    public void delete(String bucket, String objectKey) {
        requireConfigured();
        String escapedObjectKey = objectKey
                .replace("\\", "\\\\")
                .replace("\"", "\\\"");
        String body = "{\"prefixes\":[\"" + escapedObjectKey + "\"]}";
        HttpRequest request = authorizedRequest(bucketObjectUri(bucket))
                .header("Content-Type", "application/json")
                .method("DELETE", HttpRequest.BodyPublishers.ofString(body))
                .build();
        send(request, "Storage 삭제에 실패했습니다.");
    }

    private HttpRequest.Builder authorizedRequest(URI uri) {
        return HttpRequest.newBuilder(uri)
                .header("Authorization", "Bearer " + secretKey)
                .header("apikey", secretKey);
    }

    private void send(HttpRequest request, String message) {
        try {
            HttpResponse<Void> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.discarding()
            );
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new StorageOperationException(message);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new StorageOperationException(message, exception);
        } catch (IOException exception) {
            throw new StorageOperationException(message, exception);
        }
    }

    private URI objectUri(String bucket, String objectKey) {
        String encodedBucket = encodeSegment(bucket);
        String encodedKey = java.util.Arrays.stream(objectKey.split("/"))
                .map(SupabaseCareerDocumentStorage::encodeSegment)
                .collect(java.util.stream.Collectors.joining("/"));
        return URI.create(projectUrl + "/storage/v1/object/" + encodedBucket + "/" + encodedKey);
    }

    private URI bucketObjectUri(String bucket) {
        return URI.create(projectUrl + "/storage/v1/object/" + encodeSegment(bucket));
    }

    private void requireConfigured() {
        if (projectUrl.isBlank() || secretKey.isBlank()) {
            throw new StorageOperationException("Supabase Storage 서버 설정이 필요합니다.");
        }
    }

    private static String encodeSegment(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }

    private static String stripTrailingSlash(String value) {
        return value == null ? "" : value.replaceFirst("/+$", "");
    }
}
