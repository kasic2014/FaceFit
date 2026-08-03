package com.facefit.backend.interview.domain;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;

@Getter
@Entity
@Table(name = "interview_reports")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewReport {

    @Id
    @Column(name = "report_id", nullable = false, updatable = false)
    private UUID reportId;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "session_id", nullable = false, updatable = false)
    private InterviewSession session;

    @Column(name = "schema_version", nullable = false, length = 20, updatable = false)
    private String schemaVersion;

    @Column(name = "input_hash", nullable = false, length = 64, updatable = false)
    private String inputHash;

    @Column(name = "overall_score", nullable = false, precision = 4, scale = 1)
    private BigDecimal overallScore;

    @Column(name = "gaze_score", nullable = false, precision = 4, scale = 1)
    private BigDecimal gazeScore;

    @Column(name = "posture_score", nullable = false, precision = 4, scale = 1)
    private BigDecimal postureScore;

    @Column(name = "speech_score", precision = 4, scale = 1)
    private BigDecimal speechScore;

    @Column(name = "content_score", nullable = false, precision = 4, scale = 1)
    private BigDecimal contentScore;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "strengths", nullable = false, columnDefinition = "jsonb")
    private JsonNode strengths;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "improvements", nullable = false, columnDefinition = "jsonb")
    private JsonNode improvements;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "question_feedback", nullable = false, columnDefinition = "jsonb")
    private JsonNode questionFeedback;

    @Column(name = "generated_at", nullable = false, updatable = false)
    private OffsetDateTime generatedAt;

    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    @Version
    @ColumnDefault("0")
    @Column(name = "row_version", nullable = false)
    private long rowVersion;

    private InterviewReport(
            UUID reportId,
            InterviewSession session,
            String schemaVersion,
            String inputHash,
            BigDecimal overallScore,
            BigDecimal gazeScore,
            BigDecimal postureScore,
            BigDecimal speechScore,
            BigDecimal contentScore,
            JsonNode strengths,
            JsonNode improvements,
            JsonNode questionFeedback,
            OffsetDateTime generatedAt
    ) {
        this.reportId = Objects.requireNonNull(reportId);
        this.session = Objects.requireNonNull(session);
        this.schemaVersion = Objects.requireNonNull(schemaVersion);
        this.inputHash = Objects.requireNonNull(inputHash);
        this.overallScore = Objects.requireNonNull(overallScore);
        this.gazeScore = Objects.requireNonNull(gazeScore);
        this.postureScore = Objects.requireNonNull(postureScore);
        this.speechScore = speechScore;
        this.contentScore = Objects.requireNonNull(contentScore);
        this.strengths = Objects.requireNonNull(strengths);
        this.improvements = Objects.requireNonNull(improvements);
        this.questionFeedback = Objects.requireNonNull(questionFeedback);
        this.generatedAt = Objects.requireNonNull(generatedAt);
    }

    public static InterviewReport create(
            UUID reportId,
            InterviewSession session,
            String schemaVersion,
            String inputHash,
            BigDecimal overallScore,
            BigDecimal gazeScore,
            BigDecimal postureScore,
            BigDecimal speechScore,
            BigDecimal contentScore,
            JsonNode strengths,
            JsonNode improvements,
            JsonNode questionFeedback,
            OffsetDateTime generatedAt
    ) {
        return new InterviewReport(
                reportId,
                session,
                schemaVersion,
                inputHash,
                overallScore,
                gazeScore,
                postureScore,
                speechScore,
                contentScore,
                strengths,
                improvements,
                questionFeedback,
                generatedAt
        );
    }

    @PrePersist
    void initializeTimestamps() {
        OffsetDateTime now = OffsetDateTime.now();
        createdAt = createdAt == null ? now : createdAt;
        updatedAt = updatedAt == null ? now : updatedAt;
    }

    @PreUpdate
    void updateTimestamp() {
        updatedAt = OffsetDateTime.now();
    }
}
