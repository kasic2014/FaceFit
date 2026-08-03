package com.facefit.backend.jobposting.storage;

import com.facefit.backend.common.exception.StorageOperationException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.stream.Collectors;

@Component
public class SupabaseJobPostingStorage implements JobPostingStorage {

    private static final int MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024;

    private final String projectUrl;
    private final String secretKey;
    private final HttpClient httpClient;

    @Autowired
    public SupabaseJobPostingStorage(
            @Value("${facefit.storage.supabase.project-url:}") String projectUrl,
            @Value("${facefit.storage.supabase.secret-key:}") String secretKey
    ) {
        this(projectUrl, secretKey, HttpClient.newHttpClient());
    }

    SupabaseJobPostingStorage(String projectUrl, String secretKey, HttpClient httpClient) {
        this.projectUrl = stripTrailingSlash(projectUrl);
        this.secretKey = secretKey == null ? "" : secretKey;
        this.httpClient = httpClient;
    }

    @Override
    public void upload(String bucket, String objectKey, String mimeType, byte[] content) {
        requireConfigured();
        HttpRequest request = authorizedRequest(objectUri(bucket, objectKey, false))
                .header("Content-Type", mimeType)
                .header("x-upsert", "false")
                .POST(HttpRequest.BodyPublishers.ofByteArray(content))
                .build();
        sendWithoutBody(request, "JOB_STORAGE_UPLOAD_FAILED");
    }

    @Override
    public byte[] download(String bucket, String objectKey) {
        requireConfigured();
        HttpRequest request = authorizedRequest(objectUri(bucket, objectKey, true))
                .GET()
                .build();
        try {
            HttpResponse<InputStream> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.ofInputStream()
            );
            if (!isSuccessful(response.statusCode())) {
                closeQuietly(response.body());
                throw new StorageOperationException("JOB_STORAGE_DOWNLOAD_FAILED");
            }
            try (InputStream input = response.body()) {
                byte[] content = input.readNBytes(MAX_DOWNLOAD_BYTES + 1);
                if (content.length > MAX_DOWNLOAD_BYTES) {
                    throw new StorageOperationException("JOB_STORAGE_DOWNLOAD_TOO_LARGE");
                }
                return content;
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new StorageOperationException("JOB_STORAGE_DOWNLOAD_INTERRUPTED", exception);
        } catch (IOException exception) {
            throw new StorageOperationException("JOB_STORAGE_DOWNLOAD_FAILED", exception);
        }
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
        sendWithoutBody(request, "JOB_STORAGE_DELETE_FAILED");
    }

    private void sendWithoutBody(HttpRequest request, String errorCode) {
        try {
            HttpResponse<Void> response = httpClient.send(
                    request,
                    HttpResponse.BodyHandlers.discarding()
            );
            if (!isSuccessful(response.statusCode())) {
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

    private URI objectUri(String bucket, String objectKey, boolean authenticatedDownload) {
        String route = authenticatedDownload ? "/storage/v1/object/authenticated/" : "/storage/v1/object/";
        return URI.create(projectUrl + route + encodeSegment(bucket) + "/" + encodeObjectKey(objectKey));
    }

    private URI bucketObjectUri(String bucket) {
        return URI.create(projectUrl + "/storage/v1/object/" + encodeSegment(bucket));
    }

    private String encodeObjectKey(String objectKey) {
        return Arrays.stream(objectKey.split("/"))
                .map(SupabaseJobPostingStorage::encodeSegment)
                .collect(Collectors.joining("/"));
    }

    private void requireConfigured() {
        if (projectUrl.isBlank() || secretKey.isBlank()) {
            throw new StorageOperationException("SUPABASE_STORAGE_NOT_CONFIGURED");
        }
    }

    private static boolean isSuccessful(int status) {
        return status >= 200 && status < 300;
    }

    private static String encodeSegment(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }

    private static String stripTrailingSlash(String value) {
        return value == null ? "" : value.replaceFirst("/+$", "");
    }

    private static void closeQuietly(InputStream stream) {
        try {
            stream.close();
        } catch (IOException ignored) {
            // Response body is intentionally discarded.
        }
    }
}
