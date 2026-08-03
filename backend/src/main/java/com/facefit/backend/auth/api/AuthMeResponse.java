package com.facefit.backend.auth.api;

import com.facefit.backend.member.domain.MemberStatus;
import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.member.domain.Profile;

import java.util.UUID;

public record AuthMeResponse(
        UUID userId,
        MemberStatus memberStatus,
        OnboardingStatus onboardingStatus,
        boolean voiceAnalysisConsent,
        String nextAction
) {

    public static AuthMeResponse from(Profile profile) {
        return new AuthMeResponse(
                profile.getUserId(),
                profile.getMemberStatus(),
                profile.getOnboardingStatus(),
                profile.isVoiceAnalysisConsented(),
                nextAction(profile)
        );
    }

    private static String nextAction(Profile profile) {
        if (profile.getMemberStatus() != MemberStatus.ACTIVE) {
            return "RELOGIN";
        }
        return profile.getOnboardingStatus() == OnboardingStatus.COMPLETED
                ? "GO_TO_SERVICE"
                : "COMPLETE_ONBOARDING";
    }
}
