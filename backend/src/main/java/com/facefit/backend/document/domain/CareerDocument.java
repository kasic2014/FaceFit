package com.facefit.backend.document.domain;

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
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.ColumnDefault;

import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;

@Getter
@Entity
@Table(name = "career_documents")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CareerDocument {

    @Id
    @Column(name = "document_id", nullable = false, updatable = false)
    private UUID documentId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, updatable = false)
    private Profile profile;

    @Enumerated(EnumType.STRING)
    @Column(name = "document_type", nullable = false, length = 30)
    private CareerDocumentType documentType;

    @Column(name = "original_file_name", nullable = false, columnDefinition = "TEXT")
    private String originalFileName;

    @Column(name = "storage_bucket", nullable = false, length = 100)
    private String storageBucket;

    @Column(name = "storage_path", nullable = false, unique = true, columnDefinition = "TEXT")
    private String storagePath;

    @Column(name = "mime_type", nullable = false, length = 100)
    private String mimeType;

    @Column(name = "file_size_bytes", nullable = false)
    private long fileSizeBytes;

    @Enumerated(EnumType.STRING)
    @ColumnDefault("'PROCESSING'")
    @Column(name = "processing_status", nullable = false, length = 20)
    private DocumentProcessingStatus processingStatus;

    @Column(name = "extracted_text", columnDefinition = "TEXT")
    private String extractedText;

    @Column(name = "processing_error", columnDefinition = "TEXT")
    private String processingError;

    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    @Column(name = "deleted_at")
    private OffsetDateTime deletedAt;

    private CareerDocument(
            UUID documentId,
            Profile profile,
            CareerDocumentType documentType,
            String originalFileName,
            String storageBucket,
            String storagePath,
            String mimeType,
            long fileSizeBytes
    ) {
        this.documentId = Objects.requireNonNull(documentId);
        this.profile = Objects.requireNonNull(profile);
        this.documentType = Objects.requireNonNull(documentType);
        this.originalFileName = Objects.requireNonNull(originalFileName);
        this.storageBucket = Objects.requireNonNull(storageBucket);
        this.storagePath = Objects.requireNonNull(storagePath);
        this.mimeType = Objects.requireNonNull(mimeType);
        this.fileSizeBytes = fileSizeBytes;
        this.processingStatus = DocumentProcessingStatus.PROCESSING;
    }

    public static CareerDocument create(
            UUID documentId,
            Profile profile,
            CareerDocumentType documentType,
            String originalFileName,
            String storageBucket,
            String storagePath,
            String mimeType,
            long fileSizeBytes
    ) {
        return new CareerDocument(
                documentId,
                profile,
                documentType,
                originalFileName,
                storageBucket,
                storagePath,
                mimeType,
                fileSizeBytes
        );
    }

    public void softDelete(OffsetDateTime deletedAt) {
        if (this.deletedAt == null) {
            this.deletedAt = Objects.requireNonNull(deletedAt);
            this.updatedAt = deletedAt;
        }
    }

    public void restore() {
        this.deletedAt = null;
        this.updatedAt = OffsetDateTime.now();
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
