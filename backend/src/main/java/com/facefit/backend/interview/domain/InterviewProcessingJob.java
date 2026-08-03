package com.facefit.backend.interview.domain;

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

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;

@Getter
@Entity
@Table(name = "interview_processing_jobs")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewProcessingJob {

    public static final int MAX_ATTEMPTS = 3;

    @Id
    @Column(name = "job_id", nullable = false, updatable = false)
    private UUID jobId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "session_id", nullable = false, updatable = false)
    private InterviewSession session;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "answer_id", updatable = false)
    private InterviewAnswer answer;

    @Enumerated(EnumType.STRING)
    @Column(name = "job_type", nullable = false, length = 30, updatable = false)
    private InterviewJobType type;

    @Enumerated(EnumType.STRING)
    @ColumnDefault("'QUEUED'")
    @Column(name = "job_status", nullable = false, length = 20)
    private InterviewJobStatus status;

    @ColumnDefault("0")
    @Column(name = "attempt_count", nullable = false)
    private int attemptCount;

    @ColumnDefault("3")
    @Column(name = "max_attempts", nullable = false, updatable = false)
    private int maxAttempts;

    @ColumnDefault("now()")
    @Column(name = "next_retry_at", nullable = false)
    private OffsetDateTime nextRetryAt;

    @Column(name = "worker_token")
    private UUID workerToken;

    @Column(name = "locked_at")
    private OffsetDateTime lockedAt;

    @Column(name = "completed_at")
    private OffsetDateTime completedAt;

    @Column(name = "failure_code", length = 100)
    private String failureCode;

    @Column(name = "failure_retryable")
    private Boolean failureRetryable;

    @Column(name = "result_payload", columnDefinition = "TEXT")
    private String resultPayload;

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

    private InterviewProcessingJob(
            UUID jobId,
            InterviewSession session,
            InterviewAnswer answer,
            InterviewJobType type
    ) {
        this.jobId = Objects.requireNonNull(jobId);
        this.session = Objects.requireNonNull(session);
        this.answer = answer;
        this.type = Objects.requireNonNull(type);
        this.status = InterviewJobStatus.QUEUED;
        this.maxAttempts = MAX_ATTEMPTS;
        this.nextRetryAt = OffsetDateTime.now();
    }

    public static InterviewProcessingJob questionGeneration(
            UUID jobId,
            InterviewSession session
    ) {
        return new InterviewProcessingJob(
                jobId,
                session,
                null,
                InterviewJobType.QUESTION_GENERATION
        );
    }

    public static InterviewProcessingJob answerAnalysis(
            UUID jobId,
            InterviewSession session,
            InterviewAnswer answer,
            InterviewJobType type
    ) {
        if (type == InterviewJobType.QUESTION_GENERATION
                || type == InterviewJobType.REPORT_GENERATION) {
            throw new IllegalArgumentException("답변 작업 유형이 아닙니다.");
        }
        return new InterviewProcessingJob(jobId, session, answer, type);
    }

    public static InterviewProcessingJob reportGeneration(
            UUID jobId,
            InterviewSession session
    ) {
        return new InterviewProcessingJob(
                jobId,
                session,
                null,
                InterviewJobType.REPORT_GENERATION
        );
    }

    public boolean claim(UUID token, OffsetDateTime now, Duration staleAfter) {
        boolean dueQueued = status == InterviewJobStatus.QUEUED
                && !nextRetryAt.isAfter(now);
        boolean staleProcessing = status == InterviewJobStatus.PROCESSING
                && lockedAt != null
                && !lockedAt.plus(staleAfter).isAfter(now);
        if ((!dueQueued && !staleProcessing) || attemptCount >= maxAttempts) {
            return false;
        }
        status = InterviewJobStatus.PROCESSING;
        workerToken = Objects.requireNonNull(token);
        lockedAt = now;
        attemptCount++;
        failureCode = null;
        failureRetryable = null;
        return true;
    }

    public boolean failExhaustedStaleClaim(
            OffsetDateTime now,
            Duration staleAfter
    ) {
        if (status != InterviewJobStatus.PROCESSING
                || lockedAt == null
                || lockedAt.plus(staleAfter).isAfter(now)
                || attemptCount < maxAttempts) {
            return false;
        }
        status = InterviewJobStatus.FAILED;
        failureCode = "WORKER_TIMEOUT";
        failureRetryable = true;
        completedAt = now;
        clearClaim();
        return true;
    }

    public boolean isOwnedBy(UUID token) {
        return status == InterviewJobStatus.PROCESSING
                && Objects.equals(workerToken, token);
    }

    public void succeed(UUID token, String payload, OffsetDateTime now) {
        requireToken(token);
        status = InterviewJobStatus.SUCCEEDED;
        resultPayload = payload;
        completedAt = now;
        clearClaim();
    }

    public void retry(UUID token, String code, OffsetDateTime now) {
        requireToken(token);
        if (attemptCount >= maxAttempts) {
            fail(token, code, true, now);
            return;
        }
        status = InterviewJobStatus.QUEUED;
        failureCode = code;
        failureRetryable = true;
        nextRetryAt = now.plusSeconds(attemptCount == 1 ? 2 : 10);
        clearClaim();
    }

    public void fail(
            UUID token,
            String code,
            boolean retryable,
            OffsetDateTime now
    ) {
        requireToken(token);
        status = InterviewJobStatus.FAILED;
        failureCode = code;
        failureRetryable = retryable;
        completedAt = now;
        clearClaim();
    }

    private void requireToken(UUID token) {
        if (!isOwnedBy(token)) {
            throw new IllegalStateException("작업 획득 토큰이 일치하지 않습니다.");
        }
    }

    private void clearClaim() {
        workerToken = null;
        lockedAt = null;
    }

    @PrePersist
    void initializeTimestamps() {
        OffsetDateTime now = OffsetDateTime.now();
        createdAt = createdAt == null ? now : createdAt;
        updatedAt = updatedAt == null ? now : updatedAt;
        nextRetryAt = nextRetryAt == null ? now : nextRetryAt;
    }

    @PreUpdate
    void updateTimestamp() {
        updatedAt = OffsetDateTime.now();
    }
}
