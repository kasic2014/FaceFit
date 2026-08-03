package com.facefit.backend.interview.integration.http;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.facefit.backend.interview.integration.AnalysisResult;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.integration.SttResult;

import java.io.IOException;
import java.io.InputStream;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Supplier;

public final class FaceFitAiHttpClient {

    private static final String STT_PATH = "/internal/v1/analyses/stt";
    private static final String CV_PATH = "/internal/v1/analyses/cv";
    private static final String VOICE_PATH = "/internal/v1/analyses/voice";
    private static final String CONTENT_PATH = "/internal/v1/analyses/content";
    private static final String SCHEMA_VERSION = "1.0";
    private static final int MAX_TRANSCRIPT_CHARS = 50_000;
    private static final int MAX_MODEL_VERSION_CHARS = 100;
    private static final double MAX_DURATION_SECONDS = 300.0;
    private static final Map<Integer, AiErrorCode> ERROR_CODES = Map.of(
            400, AiErrorCode.INVALID_REQUEST,
            401, AiErrorCode.UNAUTHORIZED,
            413, AiErrorCode.PAYLOAD_TOO_LARGE,
            415, AiErrorCode.UNSUPPORTED_MEDIA_TYPE,
            422, AiErrorCode.MEDIA_ANALYSIS_FAILED,
            500, AiErrorCode.MODEL_ERROR,
            503, AiErrorCode.ANALYSIS_UNAVAILABLE,
            504, AiErrorCode.MODEL_TIMEOUT
    );

    private final AiHttpProperties properties;
    private final ObjectMapper objectMapper;
    private final AiHttpTransport transport;
    private final Supplier<UUID> requestIdFactory;

    FaceFitAiHttpClient(
            AiHttpProperties properties,
            ObjectMapper objectMapper,
            AiHttpTransport transport
    ) {
        this(properties, objectMapper, transport, UUID::randomUUID);
    }

    FaceFitAiHttpClient(
            AiHttpProperties properties,
            ObjectMapper objectMapper,
            AiHttpTransport transport,
            Supplier<UUID> requestIdFactory
    ) {
        this.properties = properties;
        this.objectMapper = objectMapper.copy()
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
        this.transport = transport;
        this.requestIdFactory = requestIdFactory;
    }

    public PortResult<SttResult> transcribe(
            UUID answerId,
            String mimeType,
            InputStream media
    ) {
        if (answerId == null || media == null || !supportedMimeType(mimeType)) {
            return PortResult.permanentFailure("AI_REQUEST_INVALID");
        }
        UUID requestId = requestIdFactory.get();
        try {
            HttpRequest request = requestBuilder(STT_PATH, requestId)
                    .header(
                            "Content-Type",
                            "multipart/form-data; boundary="
                                    + multipartBoundary(requestId)
                    )
                    .POST(sttMultipart(
                            requestId,
                            answerId,
                            mimeType,
                            media
                    ))
                    .build();
            HttpResponse<InputStream> response = transport.send(request);
            return mapSttResponse(response, requestId, answerId);
        } catch (HttpTimeoutException | ConnectException exception) {
            return PortResult.retryableFailure("AI_NETWORK_TIMEOUT");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return PortResult.retryableFailure("AI_NETWORK_INTERRUPTED");
        } catch (IOException exception) {
            return PortResult.retryableFailure("AI_NETWORK_ERROR");
        } catch (IllegalStateException | IllegalArgumentException exception) {
            return PortResult.permanentFailure("AI_CLIENT_NOT_CONFIGURED");
        } catch (RuntimeException exception) {
            return PortResult.permanentFailure("AI_RESPONSE_CONTRACT_VIOLATION");
        }
    }

    public PortResult<AnalysisResult> analyzeCv(
            UUID answerId,
            String mimeType,
            InputStream media
    ) {
        return analyzeUnavailableMedia(CV_PATH, answerId, mimeType, media);
    }

    public PortResult<AnalysisResult> analyzeVoice(
            UUID answerId,
            String mimeType,
            InputStream media
    ) {
        return analyzeUnavailableMedia(VOICE_PATH, answerId, mimeType, media);
    }

    public PortResult<AnalysisResult> analyzeContent(
            UUID answerId,
            String question,
            String transcript
    ) {
        if (answerId == null
                || question == null
                || question.isBlank()
                || transcript == null
                || transcript.isBlank()
                || transcript.codePointCount(0, transcript.length())
                > MAX_TRANSCRIPT_CHARS) {
            return PortResult.permanentFailure("AI_REQUEST_INVALID");
        }
        UUID requestId = requestIdFactory.get();
        try {
            byte[] body = objectMapper.writeValueAsBytes(
                    new ContentRequest(
                            answerId,
                            question,
                            transcript,
                            null
                    )
            );
            HttpRequest request = requestBuilder(CONTENT_PATH, requestId)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                    .build();
            return mapUnavailableResponse(
                    transport.send(request),
                    requestId
            );
        } catch (HttpTimeoutException | ConnectException exception) {
            return PortResult.retryableFailure("AI_NETWORK_TIMEOUT");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return PortResult.retryableFailure("AI_NETWORK_INTERRUPTED");
        } catch (JsonProcessingException exception) {
            return PortResult.permanentFailure("AI_REQUEST_SERIALIZATION_FAILED");
        } catch (IOException exception) {
            return PortResult.retryableFailure("AI_NETWORK_ERROR");
        } catch (IllegalStateException | IllegalArgumentException exception) {
            return PortResult.permanentFailure("AI_CLIENT_NOT_CONFIGURED");
        } catch (RuntimeException exception) {
            return PortResult.permanentFailure("AI_RESPONSE_CONTRACT_VIOLATION");
        }
    }

    private PortResult<AnalysisResult> analyzeUnavailableMedia(
            String path,
            UUID answerId,
            String mimeType,
            InputStream media
    ) {
        if (answerId == null || media == null || !supportedMimeType(mimeType)) {
            return PortResult.permanentFailure("AI_REQUEST_INVALID");
        }
        UUID requestId = requestIdFactory.get();
        try {
            HttpRequest request = requestBuilder(path, requestId)
                    .header(
                            "Content-Type",
                            "multipart/form-data; boundary="
                                    + multipartBoundary(requestId)
                    )
                    .POST(analysisMultipart(
                            requestId,
                            answerId,
                            mimeType,
                            media
                    ))
                    .build();
            return mapUnavailableResponse(
                    transport.send(request),
                    requestId
            );
        } catch (HttpTimeoutException | ConnectException exception) {
            return PortResult.retryableFailure("AI_NETWORK_TIMEOUT");
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            return PortResult.retryableFailure("AI_NETWORK_INTERRUPTED");
        } catch (IOException exception) {
            return PortResult.retryableFailure("AI_NETWORK_ERROR");
        } catch (IllegalStateException | IllegalArgumentException exception) {
            return PortResult.permanentFailure("AI_CLIENT_NOT_CONFIGURED");
        } catch (RuntimeException exception) {
            return PortResult.permanentFailure("AI_RESPONSE_CONTRACT_VIOLATION");
        }
    }

    private HttpRequest.Builder requestBuilder(String path, UUID requestId) {
        URI baseUri = properties.requireBaseUri();
        Duration responseTimeout = properties.getResponseTimeout();
        return HttpRequest.newBuilder(URI.create(baseUri + path))
                .timeout(responseTimeout)
                .header("Accept", "application/json")
                .header("Authorization", "Bearer " + properties.getServiceToken())
                .header("X-Request-Id", requestId.toString());
    }

    private PortResult<SttResult> mapSttResponse(
            HttpResponse<InputStream> response,
            UUID requestId,
            UUID answerId
    ) throws IOException {
        try (InputStream body = response.body()) {
            if (response.statusCode() != 200) {
                return mapError(response.statusCode(), body, requestId);
            }
            AiSttResponse payload;
            try {
                payload = objectMapper.readValue(body, AiSttResponse.class);
            } catch (IOException | RuntimeException exception) {
                return PortResult.permanentFailure(
                        "AI_RESPONSE_CONTRACT_VIOLATION"
                );
            }
            if (!validStt(payload, requestId, answerId)) {
                return PortResult.permanentFailure(
                        "AI_RESPONSE_CONTRACT_VIOLATION"
                );
            }
            return PortResult.success(new SttResult(
                    payload.schemaVersion(),
                    payload.transcript().strip(),
                    payload.modelVersion().strip(),
                    payload.language(),
                    payload.durationSec()
            ));
        }
    }

    private PortResult<AnalysisResult> mapUnavailableResponse(
            HttpResponse<InputStream> response,
            UUID requestId
    ) throws IOException {
        try (InputStream body = response.body()) {
            if (response.statusCode() >= 200 && response.statusCode() < 300) {
                return PortResult.permanentFailure("AI_UNEXPECTED_SUCCESS");
            }
            return mapError(response.statusCode(), body, requestId);
        }
    }

    private <T> PortResult<T> mapError(
            int status,
            InputStream body,
            UUID requestId
    ) {
        AiErrorCode expectedCode = ERROR_CODES.get(status);
        if (expectedCode == null) {
            return PortResult.permanentFailure("AI_RESPONSE_STATUS_UNKNOWN");
        }
        AiErrorResponse error;
        try {
            error = objectMapper.readValue(body, AiErrorResponse.class);
        } catch (IOException | RuntimeException exception) {
            return PortResult.permanentFailure("AI_ERROR_RESPONSE_INVALID");
        }
        if (error == null
                || !requestId.equals(error.requestId())
                || error.code() != expectedCode
                || error.message() == null
                || error.message().isBlank()
                || error.retryable() == null) {
            return PortResult.permanentFailure(
                    "AI_RESPONSE_CONTRACT_VIOLATION"
            );
        }
        if (status != 500 && status != 504 && error.retryable()) {
            return PortResult.permanentFailure(
                    "AI_RESPONSE_CONTRACT_VIOLATION"
            );
        }
        return error.retryable()
                ? PortResult.retryableFailure(error.code().name())
                : PortResult.permanentFailure(error.code().name());
    }

    private boolean validStt(
            AiSttResponse payload,
            UUID requestId,
            UUID answerId
    ) {
        if (payload == null
                || !requestId.equals(payload.requestId())
                || !answerId.equals(payload.answerId())
                || payload.analysisType() != AnalysisType.STT
                || !SCHEMA_VERSION.equals(payload.schemaVersion())
                || payload.modelVersion() == null
                || payload.modelVersion().isBlank()
                || payload.modelVersion().length() > MAX_MODEL_VERSION_CHARS
                || !"ko".equals(payload.language())
                || payload.transcript() == null
                || payload.transcript().isBlank()
                || payload.transcript().codePointCount(
                0,
                payload.transcript().length()
        ) > MAX_TRANSCRIPT_CHARS
                || payload.durationSec() == null
                || !Double.isFinite(payload.durationSec())
                || payload.durationSec() <= 0
                || payload.durationSec() > MAX_DURATION_SECONDS) {
            return false;
        }
        return true;
    }

    private HttpRequest.BodyPublisher sttMultipart(
            UUID requestId,
            UUID answerId,
            String mimeType,
            InputStream media
    ) {
        String boundary = multipartBoundary(requestId);
        return HttpRequest.BodyPublishers.concat(
                textPart(boundary, "answerId", answerId.toString()),
                textPart(boundary, "language", "ko"),
                mediaPart(boundary, mimeType, media),
                endBoundary(boundary)
        );
    }

    private HttpRequest.BodyPublisher analysisMultipart(
            UUID requestId,
            UUID answerId,
            String mimeType,
            InputStream media
    ) {
        String boundary = multipartBoundary(requestId);
        return HttpRequest.BodyPublishers.concat(
                textPart(boundary, "answerId", answerId.toString()),
                mediaPart(boundary, mimeType, media),
                endBoundary(boundary)
        );
    }

    private HttpRequest.BodyPublisher textPart(
            String boundary,
            String name,
            String value
    ) {
        return bytes(
                "--" + boundary + "\r\n"
                        + "Content-Disposition: form-data; name=\""
                        + name
                        + "\"\r\n\r\n"
                        + value
                        + "\r\n"
        );
    }

    private HttpRequest.BodyPublisher mediaPart(
            String boundary,
            String mimeType,
            InputStream media
    ) {
        String safeName = "video/mp4".equals(mimeType)
                ? "media.mp4"
                : "media.webm";
        AtomicBoolean supplied = new AtomicBoolean();
        return HttpRequest.BodyPublishers.concat(
                bytes(
                        "--" + boundary + "\r\n"
                                + "Content-Disposition: form-data; name=\"media\"; "
                                + "filename=\"" + safeName + "\"\r\n"
                                + "Content-Type: " + mimeType + "\r\n\r\n"
                ),
                HttpRequest.BodyPublishers.ofInputStream(() -> {
                    if (!supplied.compareAndSet(false, true)) {
                        throw new IllegalStateException(
                                "MEDIA_STREAM_ALREADY_CONSUMED"
                        );
                    }
                    return media;
                }),
                bytes("\r\n")
        );
    }

    private HttpRequest.BodyPublisher endBoundary(String boundary) {
        return bytes("--" + boundary + "--\r\n");
    }

    private HttpRequest.BodyPublisher bytes(String value) {
        return HttpRequest.BodyPublishers.ofByteArray(
                value.getBytes(StandardCharsets.UTF_8)
        );
    }

    private String multipartBoundary(UUID requestId) {
        return "facefit-" + requestId;
    }

    private boolean supportedMimeType(String mimeType) {
        return "video/mp4".equals(mimeType) || "video/webm".equals(mimeType);
    }

    private enum AnalysisType {
        STT,
        CV,
        VOICE,
        CONTENT
    }

    private enum AiErrorCode {
        INVALID_REQUEST,
        UNAUTHORIZED,
        PAYLOAD_TOO_LARGE,
        UNSUPPORTED_MEDIA_TYPE,
        MEDIA_ANALYSIS_FAILED,
        MODEL_ERROR,
        ANALYSIS_UNAVAILABLE,
        MODEL_TIMEOUT
    }

    private record AiSttResponse(
            UUID requestId,
            UUID answerId,
            AnalysisType analysisType,
            String schemaVersion,
            String modelVersion,
            String language,
            String transcript,
            Double durationSec
    ) {
    }

    private record AiErrorResponse(
            UUID requestId,
            AiErrorCode code,
            String message,
            Boolean retryable
    ) {
    }

    private record ContentRequest(
            UUID answerId,
            String question,
            String transcript,
            String jobContext
    ) {
    }
}
