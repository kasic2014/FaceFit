package com.facefit.backend.interview.integration.http;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.net.URI;
import java.time.Duration;

@ConfigurationProperties(prefix = "facefit.ai")
public class AiHttpProperties {

    private String baseUrl = "";
    private String serviceToken = "";
    private Duration connectTimeout = Duration.ofSeconds(3);
    private Duration responseTimeout = Duration.ofSeconds(60);

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl == null ? "" : baseUrl.strip();
    }

    public String getServiceToken() {
        return serviceToken;
    }

    public void setServiceToken(String serviceToken) {
        this.serviceToken = serviceToken == null ? "" : serviceToken;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getResponseTimeout() {
        return responseTimeout;
    }

    public void setResponseTimeout(Duration responseTimeout) {
        this.responseTimeout = responseTimeout;
    }

    URI requireBaseUri() {
        requireValidTimeouts();
        if (baseUrl.isBlank() || serviceToken.isBlank()) {
            throw new IllegalStateException("AI_HTTP_NOT_CONFIGURED");
        }
        URI uri;
        try {
            uri = URI.create(baseUrl.replaceFirst("/+$", ""));
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("AI_HTTP_CONFIGURATION_INVALID");
        }
        if (!("http".equalsIgnoreCase(uri.getScheme())
                || "https".equalsIgnoreCase(uri.getScheme()))
                || uri.getHost() == null
                || uri.getUserInfo() != null
                || uri.getQuery() != null
                || uri.getFragment() != null) {
            throw new IllegalStateException("AI_HTTP_CONFIGURATION_INVALID");
        }
        return uri;
    }

    void requireValidTimeouts() {
        if (connectTimeout == null
                || connectTimeout.isZero()
                || connectTimeout.isNegative()
                || responseTimeout == null
                || responseTimeout.compareTo(Duration.ofSeconds(55)) <= 0) {
            throw new IllegalStateException("AI_HTTP_CONFIGURATION_INVALID");
        }
    }

    @Override
    public String toString() {
        return "AiHttpProperties{"
                + "baseUrlConfigured=" + !baseUrl.isBlank()
                + ", serviceTokenConfigured=" + !serviceToken.isBlank()
                + ", connectTimeout=" + connectTimeout
                + ", responseTimeout=" + responseTimeout
                + '}';
    }
}
