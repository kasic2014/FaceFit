package com.facefit.backend.interview.domain;

import com.facefit.backend.member.domain.Profile;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.ColumnDefault;

import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;

@Getter
@Entity
@Table(name = "api_idempotency_records")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ApiIdempotencyRecord {

    @Id
    @Column(name = "idempotency_record_id", nullable = false, updatable = false)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, updatable = false)
    private Profile profile;

    @Column(name = "http_method", nullable = false, length = 10, updatable = false)
    private String httpMethod;

    @Column(name = "request_uri", nullable = false, length = 500, updatable = false)
    private String requestUri;

    @Column(name = "idempotency_key", nullable = false, length = 64, updatable = false)
    private String idempotencyKey;

    @Column(name = "request_hash", nullable = false, length = 64, updatable = false)
    private String requestHash;

    @Enumerated(EnumType.STRING)
    @ColumnDefault("'PROCESSING'")
    @Column(name = "processing_status", nullable = false, length = 20)
    private IdempotencyProcessingStatus status;

    @Column(name = "response_http_status")
    private Integer responseHttpStatus;

    @Column(name = "response_body", columnDefinition = "TEXT")
    private String responseBody;

    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @Column(name = "completed_at")
    private OffsetDateTime completedAt;

    @Version
    @ColumnDefault("0")
    @Column(name = "row_version", nullable = false)
    private long rowVersion;

    private ApiIdempotencyRecord(
            UUID id,
            Profile profile,
            String httpMethod,
            String requestUri,
            String idempotencyKey,
            String requestHash
    ) {
        this.id = Objects.requireNonNull(id);
        this.profile = Objects.requireNonNull(profile);
        this.httpMethod = Objects.requireNonNull(httpMethod);
        this.requestUri = Objects.requireNonNull(requestUri);
        this.idempotencyKey = Objects.requireNonNull(idempotencyKey);
        this.requestHash = Objects.requireNonNull(requestHash);
        this.status = IdempotencyProcessingStatus.PROCESSING;
    }

    public static ApiIdempotencyRecord start(
            UUID id,
            Profile profile,
            String httpMethod,
            String requestUri,
            String idempotencyKey,
            String requestHash
    ) {
        return new ApiIdempotencyRecord(
                id,
                profile,
                httpMethod,
                requestUri,
                idempotencyKey,
                requestHash
        );
    }

    public void complete(int httpStatus, String responseBody) {
        this.status = IdempotencyProcessingStatus.COMPLETED;
        this.responseHttpStatus = httpStatus;
        this.responseBody = Objects.requireNonNull(responseBody);
        this.completedAt = OffsetDateTime.now();
    }

    @PrePersist
    void initializeCreatedAt() {
        createdAt = createdAt == null ? OffsetDateTime.now() : createdAt;
    }
}
