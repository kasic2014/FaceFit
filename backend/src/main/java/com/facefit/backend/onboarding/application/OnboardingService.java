package com.facefit.backend.onboarding.application;

import com.facefit.backend.common.exception.InvalidOnboardingStateException;
import com.facefit.backend.common.exception.InvalidLegalActionsException;
import com.facefit.backend.common.exception.MemberAccessDeniedException;
import com.facefit.backend.common.exception.OnboardingRequiredException;
import com.facefit.backend.legal.domain.LegalActionType;
import com.facefit.backend.legal.domain.LegalDocument;
import com.facefit.backend.legal.domain.LegalRecordActionType;
import com.facefit.backend.legal.domain.UserLegalRecord;
import com.facefit.backend.legal.repository.LegalDocumentRepository;
import com.facefit.backend.legal.repository.UserLegalRecordRepository;
import com.facefit.backend.member.application.CurrentProfileService;
import com.facefit.backend.member.domain.MemberStatus;
import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.member.repository.ProfileRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import com.facefit.backend.onboarding.api.OnboardingRequest.LegalActionRequest;

@Service
@RequiredArgsConstructor
public class OnboardingService {

    private final CurrentProfileService currentProfileService;
    private final ProfileRepository profileRepository;
    private final LegalDocumentRepository legalDocumentRepository;
    private final UserLegalRecordRepository userLegalRecordRepository;

    @Transactional
    public Profile getCurrentOnboarding(Jwt jwt) {
        Profile profile = currentProfileService.requireActiveProfile(jwt);
        validateState(profile);
        return profile;
    }

    @Transactional
    public Profile completeCurrentOnboarding(Jwt jwt) {
        return completeCurrentOnboarding(jwt, List.of(), false);
    }

    @Transactional
    public Profile completeCurrentOnboarding(
            Jwt jwt,
            List<LegalActionRequest> legalActions
    ) {
        return completeCurrentOnboarding(jwt, legalActions, false);
    }

    @Transactional
    public Profile completeCurrentOnboarding(
            Jwt jwt,
            List<LegalActionRequest> legalActions,
            boolean voiceAnalysisConsent
    ) {
        Profile current = currentProfileService.requireActiveProfile(jwt);
        UUID userId = current.getUserId();
        Profile locked = profileRepository.findByIdForUpdate(userId)
                .orElseThrow(InvalidOnboardingStateException::new);
        if (locked.getMemberStatus() != MemberStatus.ACTIVE) {
            throw new MemberAccessDeniedException();
        }
        validateState(locked);

        List<LegalDocument> requiredDocuments = legalDocumentRepository
                .findAllByIsOnboardingRequiredTrueAndIsCurrentTrueAndEffectiveAtLessThanEqualOrderByDocumentTypeAsc(
                        OffsetDateTime.now()
                );
        Map<UUID, LegalActionRequest> submitted = indexSubmittedActions(legalActions);
        validateAndSaveActions(locked, submitted, requiredDocuments);

        locked.changeVoiceAnalysisConsent(
                voiceAnalysisConsent,
                voiceAnalysisConsent ? OffsetDateTime.now() : null
        );
        profileRepository.saveAndFlush(locked);

        if (locked.getOnboardingStatus() == OnboardingStatus.COMPLETED) {
            return locked;
        }

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

    private Map<UUID, LegalActionRequest> indexSubmittedActions(
            List<LegalActionRequest> legalActions
    ) {
        Map<UUID, LegalActionRequest> submitted = new HashMap<>();
        for (LegalActionRequest action : legalActions) {
            if (submitted.putIfAbsent(action.documentId(), action) != null) {
                throw new InvalidLegalActionsException(
                        "동일한 법률 문서를 중복 제출할 수 없습니다."
                );
            }
        }
        return submitted;
    }

    private void validateAndSaveActions(
            Profile profile,
            Map<UUID, LegalActionRequest> submitted,
            List<LegalDocument> requiredDocuments
    ) {
        Set<UUID> requiredIds = new HashSet<>();
        for (LegalDocument document : requiredDocuments) {
            requiredIds.add(document.getLegalDocumentId());
        }
        if (!submitted.keySet().containsAll(requiredIds)) {
            throw new InvalidLegalActionsException(
                    "현재 적용 중인 필수 법률 문서의 행위를 모두 제출해야 합니다."
            );
        }

        List<UserLegalRecord> newRecords = submitted.values().stream()
                .map(action -> validateAction(profile, action))
                .filter(java.util.Objects::nonNull)
                .toList();
        userLegalRecordRepository.saveAllAndFlush(newRecords);
    }

    private UserLegalRecord validateAction(Profile profile, LegalActionRequest action) {
        LegalDocument document = legalDocumentRepository
                .findByLegalDocumentIdAndIsCurrentTrueAndEffectiveAtLessThanEqual(
                        action.documentId(),
                        OffsetDateTime.now()
                )
                .orElseThrow(() -> new InvalidLegalActionsException(
                        "존재하지 않거나 현재 적용되지 않는 법률 문서입니다."
                ));
        LegalRecordActionType requiredAction = requiredRecordAction(document.getLegalActionType());
        if (action.actionType() != requiredAction) {
            throw new InvalidLegalActionsException(
                    "법률 문서에 필요한 행위와 제출된 행위가 일치하지 않습니다."
            );
        }
        if (userLegalRecordRepository
                .existsByProfile_UserIdAndLegalDocument_LegalDocumentIdAndActionType(
                        profile.getUserId(),
                        document.getLegalDocumentId(),
                        requiredAction
                )) {
            return null;
        }
        return UserLegalRecord.create(
                profile,
                document,
                requiredAction,
                "WEB_CHECKBOX",
                null,
                null
        );
    }

    private LegalRecordActionType requiredRecordAction(LegalActionType actionType) {
        return switch (actionType) {
            case CONSENT -> LegalRecordActionType.CONSENTED;
            case NOTICE -> LegalRecordActionType.ACKNOWLEDGED;
        };
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
