package com.facefit.backend.onboarding.application;

import com.facefit.backend.common.exception.InvalidOnboardingStateException;
import com.facefit.backend.common.exception.MemberAccessDeniedException;
import com.facefit.backend.common.exception.OnboardingRequiredException;
import com.facefit.backend.member.application.CurrentProfileService;
import com.facefit.backend.member.domain.MemberStatus;
import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.member.repository.ProfileRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
@RequiredArgsConstructor
public class OnboardingService {

    private final CurrentProfileService currentProfileService;
    private final ProfileRepository profileRepository;

    @Transactional
    public Profile getCurrentOnboarding(Jwt jwt) {
        Profile profile = currentProfileService.requireActiveProfile(jwt);
        validateState(profile);
        return profile;
    }

    @Transactional
    public Profile completeCurrentOnboarding(Jwt jwt) {
        Profile current = currentProfileService.requireActiveProfile(jwt);
        validateState(current);

        if (current.getOnboardingStatus() == OnboardingStatus.COMPLETED) {
            return current;
        }

        UUID userId = current.getUserId();
        profileRepository.completeOnboardingIfEligible(userId);

        Profile completed = profileRepository.findById(userId)
                .orElseThrow(InvalidOnboardingStateException::new);
        if (completed.getMemberStatus() != MemberStatus.ACTIVE) {
            throw new MemberAccessDeniedException();
        }
        validateState(completed);
        if (completed.getOnboardingStatus() != OnboardingStatus.COMPLETED) {
            throw new InvalidOnboardingStateException();
        }
        return completed;
    }

    @Transactional
    public Profile requireCompletedOnboarding(Jwt jwt) {
        Profile profile = currentProfileService.requireActiveProfile(jwt);
        validateState(profile);
        if (profile.getOnboardingStatus() != OnboardingStatus.COMPLETED) {
            throw new OnboardingRequiredException();
        }
        return profile;
    }

    private void validateState(Profile profile) {
        boolean completed = profile.getOnboardingStatus() == OnboardingStatus.COMPLETED;
        if (completed != (profile.getOnboardingCompletedAt() != null)) {
            throw new InvalidOnboardingStateException();
        }
    }
}
