package com.facefit.backend.jobposting.domain;

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
@Table(name = "job_postings")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class JobPosting {

    @Id
    @Column(name = "job_posting_id", nullable = false, updatable = false)
    private UUID jobPostingId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, updatable = false)
    private Profile profile;

    @Enumerated(EnumType.STRING)
    @Column(name = "input_type", nullable = false, length = 10, updatable = false)
    private JobPostingInputType inputType;

    @Column(name = "original_file_name", columnDefinition = "TEXT", updatable = false)
    private String originalFileName;

    @Column(name = "storage_bucket", length = 100, updatable = false)
    private String storageBucket;

    @Column(name = "storage_path", unique = true, columnDefinition = "TEXT", updatable = false)
    private String storagePath;

    @Column(name = "mime_type", length = 100, updatable = false)
    private String mimeType;

    @Column(name = "file_size_bytes", updatable = false)
    private Long fileSizeBytes;

    @Column(name = "raw_text", columnDefinition = "TEXT", updatable = false)
    private String rawText;

    @Column(name = "extracted_text", columnDefinition = "TEXT")
    private String extractedText;

    @Column(name = "company_name", columnDefinition = "TEXT")
    private String companyName;

    @Column(name = "target_role", columnDefinition = "TEXT")
    private String targetRole;

    @Column(name = "main_responsibilities", columnDefinition = "TEXT")
    private String mainResponsibilities;

    @Column(name = "qualifications", columnDefinition = "TEXT")
    private String qualifications;

    @Column(name = "preferred_qualifications", columnDefinition = "TEXT")
    private String preferredQualifications;

    @Column(name = "technologies_tools", columnDefinition = "TEXT")
    private String technologiesTools;

    @Column(name = "core_competencies", columnDefinition = "TEXT")
    private String coreCompetencies;

    @Column(name = "company_business_intro", columnDefinition = "TEXT")
    private String companyBusinessIntro;

    @Enumerated(EnumType.STRING)
    @ColumnDefault("'PROCESSING'")
    @Column(name = "processing_status", nullable = false, length = 20)
    private JobPostingProcessingStatus processingStatus;

    @Column(name = "processing_error", length = 80)
    private String processingError;

    @ColumnDefault("0")
    @Column(name = "processing_attempt_count", nullable = false)
    private int processingAttemptCount;

    @Column(name = "processing_started_at")
    private OffsetDateTime processingStartedAt;

    @Column(name = "processed_at")
    private OffsetDateTime processedAt;

    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    @Column(name = "deleted_at")
    private OffsetDateTime deletedAt;

    @Version
    @ColumnDefault("0")
    @Column(name = "row_version", nullable = false)
    private long rowVersion;

    private JobPosting(
            UUID jobPostingId,
            Profile profile,
            JobPostingInputType inputType,
            String originalFileName,
            String storageBucket,
            String storagePath,
            String mimeType,
            Long fileSizeBytes,
            String rawText
    ) {
        this.jobPostingId = Objects.requireNonNull(jobPostingId);
        this.profile = Objects.requireNonNull(profile);
        this.inputType = Objects.requireNonNull(inputType);
        this.originalFileName = originalFileName;
        this.storageBucket = storageBucket;
        this.storagePath = storagePath;
        this.mimeType = mimeType;
        this.fileSizeBytes = fileSizeBytes;
        this.rawText = rawText;
        this.processingStatus = JobPostingProcessingStatus.PROCESSING;
    }

    public static JobPosting createFile(
            UUID jobPostingId,
            Profile profile,
            String originalFileName,
            String storageBucket,
            String storagePath,
            String mimeType,
            long fileSizeBytes
    ) {
        return new JobPosting(
                jobPostingId,
                profile,
                JobPostingInputType.FILE,
                Objects.requireNonNull(originalFileName),
                Objects.requireNonNull(storageBucket),
                Objects.requireNonNull(storagePath),
                Objects.requireNonNull(mimeType),
                fileSizeBytes,
                null
        );
    }

    public static JobPosting createText(
            UUID jobPostingId,
            Profile profile,
            String rawText
    ) {
        return new JobPosting(
                jobPostingId,
                profile,
                JobPostingInputType.TEXT,
                null,
                null,
                null,
                null,
                null,
                Objects.requireNonNull(rawText)
        );
    }

    public boolean claimProcessing(OffsetDateTime now, OffsetDateTime staleBefore, int maxAttempts) {
        if (deletedAt != null
                || processingStatus != JobPostingProcessingStatus.PROCESSING
                || processingAttemptCount >= maxAttempts
                || (processingStartedAt != null && !processingStartedAt.isBefore(staleBefore))) {
            return false;
        }
        processingAttemptCount++;
        processingStartedAt = now;
        processingError = null;
        return true;
    }

    public void releaseForRetry() {
        if (deletedAt == null && processingStatus == JobPostingProcessingStatus.PROCESSING) {
            processingStartedAt = null;
        }
    }

    public void complete(String extractedText, StructuredJobPosting structured, OffsetDateTime now) {
        if (deletedAt != null || processingStatus != JobPostingProcessingStatus.PROCESSING) {
            return;
        }
        this.extractedText = extractedText;
        applyStructured(structured);
        this.processingStatus = JobPostingProcessingStatus.READY;
        this.processingError = null;
        this.processingStartedAt = null;
        this.processedAt = now;
    }

    public void fail(
            String extractedText,
            StructuredJobPosting structured,
            String errorCode,
            OffsetDateTime now
    ) {
        if (deletedAt != null || processingStatus != JobPostingProcessingStatus.PROCESSING) {
            return;
        }
        if (extractedText != null) {
            this.extractedText = extractedText;
        }
        if (structured != null) {
            applyStructured(structured);
        }
        this.processingStatus = JobPostingProcessingStatus.FAILED;
        this.processingError = Objects.requireNonNull(errorCode);
        this.processingStartedAt = null;
        this.processedAt = now;
    }

    public void applyUserPatch(
            String companyName,
            String targetRole,
            String mainResponsibilities,
            String qualifications,
            String preferredQualifications,
            String technologiesTools,
            String coreCompetencies,
            String companyBusinessIntro
    ) {
        this.companyName = companyName;
        this.targetRole = targetRole;
        this.mainResponsibilities = mainResponsibilities;
        this.qualifications = qualifications;
        this.preferredQualifications = preferredQualifications;
        this.technologiesTools = technologiesTools;
        this.coreCompetencies = coreCompetencies;
        this.companyBusinessIntro = companyBusinessIntro;
        if (new StructuredJobPosting(
                companyName,
                targetRole,
                mainResponsibilities,
                qualifications,
                preferredQualifications,
                technologiesTools,
                coreCompetencies,
                companyBusinessIntro
        ).hasRequiredFields()) {
            this.processingStatus = JobPostingProcessingStatus.READY;
            this.processingError = null;
            this.processedAt = OffsetDateTime.now();
        }
    }

    public void softDelete(OffsetDateTime now) {
        if (deletedAt == null) {
            deletedAt = Objects.requireNonNull(now);
            updatedAt = now;
        }
    }

    public void restore() {
        deletedAt = null;
        updatedAt = OffsetDateTime.now();
    }

    private void applyStructured(StructuredJobPosting structured) {
        this.companyName = structured.companyName();
        this.targetRole = structured.targetRole();
        this.mainResponsibilities = structured.mainResponsibilities();
        this.qualifications = structured.qualifications();
        this.preferredQualifications = structured.preferredQualifications();
        this.technologiesTools = structured.technologiesTools();
        this.coreCompetencies = structured.coreCompetencies();
        this.companyBusinessIntro = structured.companyBusinessIntro();
    }

    @PrePersist
    void initializeTimestamps() {
        OffsetDateTime now = OffsetDateTime.now();
        if (createdAt == null) {
            createdAt = now;
        }
        if (updatedAt == null) {
            updatedAt = now;
        }
    }

    @PreUpdate
    void updateTimestamp() {
        updatedAt = OffsetDateTime.now();
    }
}
