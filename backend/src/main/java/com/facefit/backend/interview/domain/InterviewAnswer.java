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
import jakarta.persistence.PreUpdate;
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
@Table(name = "interview_answers")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewAnswer {

    @Id
    @Column(name = "answer_id", nullable = false, updatable = false)
    private UUID answerId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "session_id", nullable = false, updatable = false)
    private InterviewSession session;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "turn_id", nullable = false, updatable = false)
    private InterviewTurn turn;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, updatable = false)
    private Profile profile;

    @Enumerated(EnumType.STRING)
    @Column(name = "storage_provider", nullable = false, length = 20, updatable = false)
    private StorageProvider storageProvider;

    @Column(name = "storage_bucket", nullable = false, length = 100, updatable = false)
    private String storageBucket;

    @Column(name = "storage_path", nullable = false, columnDefinition = "TEXT", updatable = false)
    private String storagePath;

    @Column(name = "storage_url", columnDefinition = "TEXT", updatable = false)
    private String storageUrl;

    @Column(name = "mime_type", nullable = false, length = 100, updatable = false)
    private String mimeType;

    @Column(name = "file_size_bytes", nullable = false, updatable = false)
    private long fileSizeBytes;

    @Column(name = "file_sha256", nullable = false, length = 64, updatable = false)
    private String fileSha256;

    @Column(name = "recorded_duration_seconds", nullable = false, updatable = false)
    private int recordedDurationSeconds;

    @Column(name = "detected_duration_millis", nullable = false, updatable = false)
    private long detectedDurationMillis;

    @Enumerated(EnumType.STRING)
    @Column(name = "ended_by", nullable = false, length = 30, updatable = false)
    private AnswerEndedBy endedBy;

    @Enumerated(EnumType.STRING)
    @ColumnDefault("'UPLOADING'")
    @Column(name = "answer_status", nullable = false, length = 30)
    private InterviewAnswerStatus status;

    @Column(name = "transcript", columnDefinition = "TEXT")
    private String transcript;

    @Column(name = "transcript_schema_version", length = 20)
    private String transcriptSchemaVersion;

    @ColumnDefault("false")
    @Column(name = "next_question_ready", nullable = false)
    private boolean nextQuestionReady;

    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @Column(name = "confirmed_at")
    private OffsetDateTime confirmedAt;

    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    @Version
    @ColumnDefault("0")
    @Column(name = "row_version", nullable = false)
    private long rowVersion;

    private InterviewAnswer(
            UUID answerId,
            InterviewSession session,
            InterviewTurn turn,
            Profile profile,
            StorageProvider storageProvider,
            String storageBucket,
            String storagePath,
            String storageUrl,
            String mimeType,
            long fileSizeBytes,
            String fileSha256,
            int recordedDurationSeconds,
            long detectedDurationMillis,
            AnswerEndedBy endedBy
    ) {
        this.answerId = Objects.requireNonNull(answerId);
        this.session = Objects.requireNonNull(session);
        this.turn = Objects.requireNonNull(turn);
        this.profile = Objects.requireNonNull(profile);
        this.storageProvider = Objects.requireNonNull(storageProvider);
        this.storageBucket = Objects.requireNonNull(storageBucket);
        this.storagePath = Objects.requireNonNull(storagePath);
        this.storageUrl = storageUrl;
        this.mimeType = Objects.requireNonNull(mimeType);
        this.fileSizeBytes = fileSizeBytes;
        this.fileSha256 = Objects.requireNonNull(fileSha256);
        this.recordedDurationSeconds = recordedDurationSeconds;
        this.detectedDurationMillis = detectedDurationMillis;
        this.endedBy = Objects.requireNonNull(endedBy);
        this.status = InterviewAnswerStatus.UPLOADING;
    }

    public static InterviewAnswer reserve(
            UUID answerId,
            InterviewSession session,
            InterviewTurn turn,
            Profile profile,
            StorageProvider storageProvider,
            String storageBucket,
            String storagePath,
            String storageUrl,
            String mimeType,
            long fileSizeBytes,
            String fileSha256,
            int recordedDurationSeconds,
            long detectedDurationMillis,
            AnswerEndedBy endedBy
    ) {
        return new InterviewAnswer(
                answerId,
                session,
                turn,
                profile,
                storageProvider,
                storageBucket,
                storagePath,
                storageUrl,
                mimeType,
                fileSizeBytes,
                fileSha256,
                recordedDurationSeconds,
                detectedDurationMillis,
                endedBy
        );
    }

    public void confirm() {
        status = InterviewAnswerStatus.QUEUED;
        nextQuestionReady = true;
        confirmedAt = OffsetDateTime.now();
    }

    public void markProcessing() {
        if (status == InterviewAnswerStatus.QUEUED) {
            status = InterviewAnswerStatus.PROCESSING;
        }
    }

    public void updateProcessingOutcome(
            boolean allSucceeded,
            boolean anyActive,
            boolean anyFailed
    ) {
        if (allSucceeded) {
            status = InterviewAnswerStatus.COMPLETED;
        } else if (anyActive) {
            status = InterviewAnswerStatus.PROCESSING;
        } else if (anyFailed) {
            status = InterviewAnswerStatus.FAILED;
        }
    }

    public void attachTranscript(String schemaVersion, String transcript) {
        this.transcriptSchemaVersion = Objects.requireNonNull(schemaVersion);
        this.transcript = Objects.requireNonNull(transcript);
    }

    public boolean isConfirmed() {
        return status != InterviewAnswerStatus.UPLOADING && confirmedAt != null;
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
