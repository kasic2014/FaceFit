package com.facefit.backend.interview.integration.http;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.facefit.backend.interview.integration.AnalysisResult;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.integration.SttResult;
import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import javax.net.ssl.SSLSession;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpHeaders;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class FaceFitAiHttpClientTest {

    private static final UUID REQUEST_ID = UUID.fromString(
            "10000000-0000-0000-0000-000000000001"
    );
    private static final UUID ANSWER_ID = UUID.fromString(
            "20000000-0000-0000-0000-000000000002"
    );

    @Test
    void bindsComposeServiceNameAsBaseUrl() {
        var source = new MapConfigurationPropertySource(Map.of(
                "facefit.ai.base-url", "http://analysis-server:8001",
                "facefit.ai.service-token", "test-only-token",
                "facefit.ai.connect-timeout", "3s",
                "facefit.ai.response-timeout", "60s"
        ));

        AiHttpProperties properties = new Binder(source)
                .bind("facefit.ai", Bindable.of(AiHttpProperties.class))
                .orElseThrow(() -> new AssertionError("binding failed"));

        assertThat(properties.requireBaseUri())
                .isEqualTo(URI.create("http://analysis-server:8001"));
        assertThat(properties.toString()).doesNotContain("test-only-token");
    }

    @Test
    void missingBaseUrlOrTokenFailsClosed() {
        AiHttpProperties properties = new AiHttpProperties();

        assertThatThrownBy(properties::requireBaseUri)
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("AI_HTTP_NOT_CONFIGURED");
    }

    @Test
    void mapsSttSuccessContract() {
        String body = """
                {
                  "requestId": "%s",
                  "answerId": "%s",
                  "analysisType": "STT",
                  "schemaVersion": "1.0",
                  "modelVersion": "faster-whisper:test",
                  "language": "ko",
                  "transcript": "테스트 답변",
                  "durationSec": 12.3
                }
                """.formatted(REQUEST_ID, ANSWER_ID);
        FaceFitAiHttpClient client = client(request -> response(200, body));

        PortResult<SttResult> result = client.transcribe(
                ANSWER_ID,
                URI.create("https://kr.object.ncloudstorage.com/bucket/key?X-Amz-Signature=test"),
                "video/mp4",
                3,
                30
        );

        assertThat(result).isInstanceOf(PortResult.Success.class);
        SttResult value = ((PortResult.Success<SttResult>) result).value();
        assertThat(value.transcript()).isEqualTo("테스트 답변");
    }

    @Test
    void mapsUnavailableWithoutRetry() {
        String body = """
                {
                  "requestId": "%s",
                  "code": "ANALYSIS_UNAVAILABLE",
                  "message": "Analysis is not available",
                  "retryable": false
                }
                """.formatted(REQUEST_ID);
        FaceFitAiHttpClient client = client(request -> response(503, body));

        PortResult<AnalysisResult> result = client.analyzeContent(
                ANSWER_ID,
                "질문",
                "답변"
        );

        assertThat(result).isEqualTo(
                new PortResult.PermanentFailure<AnalysisResult>(
                        "ANALYSIS_UNAVAILABLE"
                )
        );
    }

    @Test
    void mapsCvSuccessContractIntoExistingAnalysisPayload() {
        String body = """
                {
                  "requestId": "%s",
                  "answerId": "%s",
                  "analysisType": "CV",
                  "schemaVersion": "1.0",
                  "modelVersion": "mediapipe:0.10.35:test",
                  "gazeScore": 81.2,
                  "postureScore": 73.4,
                  "feedback": ["head direction proxy"]
                }
                """.formatted(REQUEST_ID, ANSWER_ID);
        FaceFitAiHttpClient client = client(request -> response(200, body));

        PortResult<AnalysisResult> result = client.analyzeCv(
                ANSWER_ID,
                URI.create("https://kr.object.ncloudstorage.com/bucket/key?X-Amz-Signature=test"),
                "video/mp4",
                3,
                30
        );

        assertThat(result).isInstanceOf(PortResult.Success.class);
        AnalysisResult value = ((PortResult.Success<AnalysisResult>) result).value();
        assertThat(value.payload().path("schemaVersion").asText()).isEqualTo("1.0");
        assertThat(value.payload().path("gazeScore").asDouble()).isEqualTo(81.2);
        assertThat(value.payload().path("postureScore").asDouble()).isEqualTo(73.4);
        assertThat(value.payload().path("feedback").get(0).asText())
                .isEqualTo("head direction proxy");
    }

    @Test
    void rejectsInvalidCvSuccessInsteadOfPersistingFakeScores() {
        String body = """
                {
                  "requestId": "%s",
                  "answerId": "%s",
                  "analysisType": "CV",
                  "schemaVersion": "1.0",
                  "modelVersion": "mediapipe:test",
                  "gazeScore": 101,
                  "postureScore": 73.4,
                  "feedback": []
                }
                """.formatted(REQUEST_ID, ANSWER_ID);
        FaceFitAiHttpClient client = client(request -> response(200, body));

        PortResult<AnalysisResult> result = client.analyzeCv(
                ANSWER_ID,
                URI.create("https://kr.object.ncloudstorage.com/bucket/key?X-Amz-Signature=test"),
                "video/mp4",
                1,
                30
        );

        assertThat(result).isEqualTo(
                new PortResult.PermanentFailure<AnalysisResult>(
                        "AI_RESPONSE_CONTRACT_VIOLATION"
                )
        );
    }

    @Test
    void mapsTimeoutToRetryableNetworkFailure() {
        FaceFitAiHttpClient client = client(request -> {
            throw new HttpTimeoutException("test timeout");
        });

        PortResult<AnalysisResult> result = client.analyzeContent(
                ANSWER_ID,
                "질문",
                "답변"
        );

        assertThat(result).isEqualTo(
                new PortResult.RetryableFailure<AnalysisResult>(
                        "AI_NETWORK_TIMEOUT"
                )
        );
    }

    @Test
    void mapsUnavailableServerToRetryableNetworkFailure() {
        FaceFitAiHttpClient client = client(request -> {
            throw new ConnectException("connection refused");
        });

        PortResult<AnalysisResult> result = client.analyzeContent(
                ANSWER_ID,
                "질문",
                "답변"
        );

        assertThat(result).isEqualTo(
                new PortResult.RetryableFailure<AnalysisResult>(
                        "AI_NETWORK_TIMEOUT"
                )
        );
    }

    private FaceFitAiHttpClient client(AiHttpTransport transport) {
        AiHttpProperties properties = new AiHttpProperties();
        properties.setBaseUrl("http://analysis-server:8001");
        properties.setServiceToken("test-only-token");
        properties.setConnectTimeout(Duration.ofSeconds(3));
        properties.setResponseTimeout(Duration.ofSeconds(60));
        return new FaceFitAiHttpClient(
                properties,
                new ObjectMapper(),
                transport,
                () -> REQUEST_ID
        );
    }

    private static HttpResponse<InputStream> response(int status, String body) {
        return new HttpResponse<>() {
            @Override
            public int statusCode() {
                return status;
            }

            @Override
            public HttpRequest request() {
                return null;
            }

            @Override
            public Optional<HttpResponse<InputStream>> previousResponse() {
                return Optional.empty();
            }

            @Override
            public HttpHeaders headers() {
                return HttpHeaders.of(Map.of(), (name, value) -> true);
            }

            @Override
            public InputStream body() {
                return new ByteArrayInputStream(
                        body.getBytes(StandardCharsets.UTF_8)
                );
            }

            @Override
            public Optional<SSLSession> sslSession() {
                return Optional.empty();
            }

            @Override
            public URI uri() {
                return URI.create("http://analysis-server:8001");
            }

            @Override
            public HttpClient.Version version() {
                return HttpClient.Version.HTTP_1_1;
            }
        };
    }
}
