package com.facefit.backend.interview.storage;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectResponse;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

import java.net.URI;
import java.nio.file.Files;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class NcloudInterviewAnswerStorageTest {

    @Test
    void bindsProviderBucketEndpointRegionAndPresignTtl() {
        var source = new MapConfigurationPropertySource(Map.of(
                "facefit.storage.interview-answers.provider", "NCLOUD",
                "facefit.storage.interview-answers.bucket", "facefit-videos",
                "facefit.storage.interview-answers.presigned-get-ttl-seconds", "300",
                "facefit.storage.ncloud.endpoint", "https://kr.object.ncloudstorage.com",
                "facefit.storage.ncloud.region", "kr-standard"
        ));
        Binder binder = new Binder(source);
        InterviewAnswerStorageProperties answers = binder.bind(
                "facefit.storage.interview-answers",
                Bindable.of(InterviewAnswerStorageProperties.class)
        ).orElseThrow(() -> new AssertionError("answer storage binding failed"));
        NcloudObjectStorageProperties ncloud = binder.bind(
                "facefit.storage.ncloud",
                Bindable.of(NcloudObjectStorageProperties.class)
        ).orElseThrow(() -> new AssertionError("ncloud binding failed"));

        assertThat(answers.getProvider().name()).isEqualTo("NCLOUD");
        assertThat(answers.getBucket()).isEqualTo("facefit-videos");
        assertThat(answers.getPresignedGetTtlSeconds()).isEqualTo(300);
        assertThat(ncloud.getEndpoint()).isEqualTo(
                URI.create("https://kr.object.ncloudstorage.com")
        );
        assertThat(ncloud.getRegion()).isEqualTo("kr-standard");
    }

    @Test
    void uploadIsFileBackedAndSetsLengthTypeAndSafeMetadata() throws Exception {
        NcloudObjectStorageProperties ncloud = configuredNcloud();
        InterviewAnswerStorageProperties answers = new InterviewAnswerStorageProperties();
        S3Client client = mock(S3Client.class);
        when(client.putObject(any(PutObjectRequest.class), any(software.amazon.awssdk.core.sync.RequestBody.class)))
                .thenReturn(PutObjectResponse.builder().build());
        S3Presigner presigner = mock(S3Presigner.class);
        NcloudInterviewAnswerStorage storage = new NcloudInterviewAnswerStorage(
                ncloud, answers, client, presigner
        );
        var path = Files.createTempFile("facefit-ncloud-test", ".webm");
        Files.write(path, new byte[]{1, 2, 3});
        try {
            storage.upload(
                    "facefit-videos", "sessions/s/turns/t/a.webm",
                    "video/webm", 3, "abc123", path
            );
        } finally {
            Files.deleteIfExists(path);
        }
        var request = org.mockito.ArgumentCaptor.forClass(PutObjectRequest.class);
        verify(client).putObject(request.capture(), any(software.amazon.awssdk.core.sync.RequestBody.class));
        assertThat(request.getValue().contentType()).isEqualTo("video/webm");
        assertThat(request.getValue().contentLength()).isEqualTo(3);
        assertThat(request.getValue().metadata())
                .containsEntry("sha256", "abc123")
                .containsEntry("extension", "webm");
        assertThat(request.getValue().acl()).isNull();
    }

    @Test
    void canonicalAndPresignedGetUsePathStyleWithoutPersistableQuery() {
        NcloudObjectStorageProperties ncloud = configuredNcloud();
        InterviewAnswerStorageProperties answers = new InterviewAnswerStorageProperties();
        NcloudObjectStorageConfiguration configuration = new NcloudObjectStorageConfiguration();
        try (S3Client client = configuration.ncloudS3Client(ncloud);
             S3Presigner presigner = configuration.ncloudS3Presigner(ncloud)) {
            NcloudInterviewAnswerStorage storage = new NcloudInterviewAnswerStorage(
                    ncloud, answers, client, presigner
            );
            URI canonical = storage.canonicalUrl(
                    "facefit-videos", "sessions/s/turns/t/a.mp4"
            );
            URI signed = storage.createPresignedGetUrl(
                    "facefit-videos", "sessions/s/turns/t/a.mp4"
            );
            assertThat(canonical.toString()).isEqualTo(
                    "https://kr.object.ncloudstorage.com/facefit-videos/sessions/s/turns/t/a.mp4"
            );
            assertThat(canonical.getRawQuery()).isNull();
            assertThat(signed.getHost()).isEqualTo("kr.object.ncloudstorage.com");
            assertThat(signed.getPath()).startsWith("/facefit-videos/sessions/");
            assertThat(signed.getRawQuery()).contains("X-Amz-Signature");
        }
    }

    private NcloudObjectStorageProperties configuredNcloud() {
        NcloudObjectStorageProperties properties = new NcloudObjectStorageProperties();
        properties.setEndpoint(URI.create("https://kr.object.ncloudstorage.com"));
        properties.setRegion("kr-standard");
        properties.setAccessKey("test-access-key");
        properties.setSecretKey("test-secret-key");
        return properties;
    }
}
