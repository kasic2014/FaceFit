package com.facefit.backend.onboarding.api;

import com.facefit.backend.legal.domain.LegalRecordActionType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

import java.util.List;
import java.util.UUID;

public record OnboardingRequest(
        @NotNull @Valid List<LegalActionRequest> legalActions,
        boolean voiceAnalysisConsent
) {
    public record LegalActionRequest(
            @NotNull UUID documentId,
            @NotNull LegalRecordActionType actionType
    ) {
    }
}
