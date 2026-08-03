package com.facefit.backend.interview.domain;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
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
@Table(name = "interview_analysis_results")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewAnalysisResult {

    @Id
    @Column(name = "analysis_result_id", nullable = false, updatable = false)
    private UUID analysisResultId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "session_id", nullable = false, updatable = false)
    private InterviewSession session;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "answer_id", nullable = false, updatable = false)
    private InterviewAnswer answer;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "source_job_id", nullable = false, updatable = false)
    private InterviewProcessingJob sourceJob;

    @Enumerated(EnumType.STRING)
    @Column(name = "analysis_type", nullable = false, length = 20, updatable = false)
    private InterviewJobType analysisType;

    @Column(name = "schema_version", nullable = false, length = 20, updatable = false)
    private String schemaVersion;

    @Column(name = "gaze_score", precision = 4, scale = 1, updatable = false)
    private BigDecimal gazeScore;

    @Column(name = "posture_score", precision = 4, scale = 1, updatable = false)
    private BigDecimal postureScore;

    @Column(name = "speech_score", precision = 4, scale = 1, updatable = false)
    private BigDecimal speechScore;

    @Column(name = "content_score", precision = 4, scale = 1, updatable = false)
    private BigDecimal contentScore;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "public_feedback", nullable = false, columnDefinition = "jsonb")
    private JsonNode publicFeedback;

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

    private InterviewAnalysisResult(
            UUID analysisResultId,
            InterviewSession session,
            InterviewAnswer answer,
            InterviewProcessingJob sourceJob,
            InterviewJobType analysisType,
            String schemaVersion,
            BigDecimal gazeScore,
            BigDecimal postureScore,
            BigDecimal speechScore,
            BigDecimal contentScore,
            JsonNode publicFeedback
    ) {
        this.analysisResultId = Objects.requireNonNull(analysisResultId);
        this.session = Objects.requireNonNull(session);
        this.answer = Objects.requireNonNull(answer);
        this.sourceJob = Objects.requireNonNull(sourceJob);
        this.analysisType = Objects.requireNonNull(analysisType);
        this.schemaVersion = Objects.requireNonNull(schemaVersion);
        this.gazeScore = gazeScore;
        this.postureScore = postureScore;
        this.speechScore = speechScore;
        this.contentScore = contentScore;
        this.publicFeedback = Objects.requireNonNull(publicFeedback);
    }

    public static InterviewAnalysisResult create(
            UUID resultId,
            InterviewSession session,
            InterviewAnswer answer,
            InterviewProcessingJob sourceJob,
            InterviewJobType type,
            String schemaVersion,
            BigDecimal gazeScore,
            BigDecimal postureScore,
            BigDecimal speechScore,
            BigDecimal contentScore,
            JsonNode publicFeedback
    ) {
        return new InterviewAnalysisResult(
                resultId,
                session,
                answer,
                sourceJob,
                type,
                schemaVersion,
                gazeScore,
                postureScore,
                speechScore,
                contentScore,
                publicFeedback
        );
    }

    public BigDecimal score(ReportAxis axis) {
        return switch (axis) {
            case GAZE -> gazeScore;
            case POSTURE -> postureScore;
            case SPEECH -> speechScore;
            case CONTENT -> contentScore;
        };
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
