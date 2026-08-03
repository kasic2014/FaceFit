package com.facefit.backend.legal.api;

import com.facefit.backend.legal.domain.LegalActionType;
import com.facefit.backend.legal.domain.LegalDocument;

import java.time.OffsetDateTime;
import java.util.UUID;

public record LegalDocumentDetailResponse(
        UUID documentId,
        String type,
        String version,
        String title,
        String content,
        boolean onboardingRequired,
        LegalActionType requiredAction,
        OffsetDateTime effectiveAt
) {
    public static LegalDocumentDetailResponse from(LegalDocument document) {
        return new LegalDocumentDetailResponse(
                document.getLegalDocumentId(),
                document.getDocumentType(),
                document.getVersion(),
                document.getTitle(),
                document.getContent(),
                document.getIsOnboardingRequired(),
                document.getLegalActionType(),
                document.getEffectiveAt()
        );
    }
}
