package com.facefit.backend.onboarding.api;

import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.member.domain.Profile;

import java.time.OffsetDateTime;

public record OnboardingResponse(
        OnboardingStatus onboardingStatus,
        OffsetDateTime onboardingCompletedAt,
        boolean voiceAnalysisConsent,
        OffsetDateTime voiceAnalysisConsentedAt,
        NextAction nextAction
) {

    public static OnboardingResponse completed(Profile profile) {
        return new OnboardingResponse(
                profile.getOnboardingStatus(),
                profile.getOnboardingCompletedAt(),
                profile.isVoiceAnalysisConsented(),
                profile.getVoiceAnalysisConsentedAt(),
                NextAction.GO_TO_SERVICE
        );
    }

    public enum NextAction {
        GO_TO_SERVICE
    }
}
