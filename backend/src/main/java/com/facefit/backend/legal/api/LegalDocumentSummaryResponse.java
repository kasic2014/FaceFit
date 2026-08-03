package com.facefit.backend.legal.api;

import com.facefit.backend.legal.domain.LegalActionType;
import com.facefit.backend.legal.domain.LegalDocument;

import java.util.UUID;

public record LegalDocumentSummaryResponse(
        UUID documentId,
        String type,
        String version,
        String title,
        boolean onboardingRequired,
        LegalActionType requiredAction
) {
    public static LegalDocumentSummaryResponse from(LegalDocument document) {
        return new LegalDocumentSummaryResponse(
                document.getLegalDocumentId(),
                document.getDocumentType(),
                document.getVersion(),
                document.getTitle(),
                document.getIsOnboardingRequired(),
                document.getLegalActionType()
        );
    }
}
