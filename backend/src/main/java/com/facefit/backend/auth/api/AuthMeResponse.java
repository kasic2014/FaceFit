package com.facefit.backend.auth.api;

import com.facefit.backend.member.domain.MemberStatus;
import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.member.domain.Profile;

import java.util.UUID;

public record AuthMeResponse(
        UUID userId,
        MemberStatus memberStatus,
        OnboardingStatus onboardingStatus
) {

    public static AuthMeResponse from(Profile profile) {
        return new AuthMeResponse(
                profile.getUserId(),
                profile.getMemberStatus(),
                profile.getOnboardingStatus()
        );
    }
}
