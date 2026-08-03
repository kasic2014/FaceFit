package com.facefit.backend.legal.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.DynamicInsert;
import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;

@Getter
@Entity
@DynamicInsert
@Table(name = "legal_documents")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class LegalDocument {

    @Id
    @Generated
    @ColumnDefault("gen_random_uuid()")
    @Column(name = "legal_document_id", nullable = false, updatable = false)
    private UUID legalDocumentId;

    @Column(name = "document_type", nullable = false, length = 40)
    private String documentType;

    @Enumerated(EnumType.STRING)
    @Column(name = "legal_action_type", nullable = false, length = 20)
    private LegalActionType legalActionType;

    @Column(name = "title", nullable = false, length = 200)
    private String title;

    @Column(name = "version", nullable = false, length = 30)
    private String version;

    @Column(name = "content", nullable = false, columnDefinition = "TEXT")
    private String content;

    @ColumnDefault("true")
    @Column(name = "is_onboarding_required", nullable = false)
    private Boolean isOnboardingRequired;

    @ColumnDefault("false")
    @Column(name = "is_current", nullable = false)
    private Boolean isCurrent;

    @Column(name = "effective_at", nullable = false)
    private OffsetDateTime effectiveAt;

    @Generated(event = EventType.INSERT)
    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    private LegalDocument(
            String documentType,
            LegalActionType legalActionType,
            String title,
            String version,
            String content,
            boolean isOnboardingRequired,
            boolean isCurrent,
            OffsetDateTime effectiveAt
    ) {
        this.documentType = Objects.requireNonNull(documentType, "documentType must not be null");
        this.legalActionType = Objects.requireNonNull(legalActionType, "legalActionType must not be null");
        this.title = Objects.requireNonNull(title, "title must not be null");
        this.version = Objects.requireNonNull(version, "version must not be null");
        this.content = Objects.requireNonNull(content, "content must not be null");
        this.isOnboardingRequired = isOnboardingRequired;
        this.isCurrent = isCurrent;
        this.effectiveAt = Objects.requireNonNull(effectiveAt, "effectiveAt must not be null");
    }

    public static LegalDocument create(
            String documentType,
            LegalActionType legalActionType,
            String title,
            String version,
            String content,
            boolean isOnboardingRequired,
            boolean isCurrent,
            OffsetDateTime effectiveAt
    ) {
        return new LegalDocument(
                documentType,
                legalActionType,
                title,
                version,
                content,
                isOnboardingRequired,
                isCurrent,
                effectiveAt
        );
    }
}
