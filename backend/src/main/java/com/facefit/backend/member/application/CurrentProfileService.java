package com.facefit.backend.member.application;

import com.facefit.backend.common.exception.MemberAccessDeniedException;
import com.facefit.backend.common.exception.ProfileProvisioningException;
import com.facefit.backend.member.domain.MemberStatus;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.member.repository.ProfileRepository;
import com.facefit.backend.security.CurrentUserExtractor;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DataAccessException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
@RequiredArgsConstructor
public class CurrentProfileService {

    private final CurrentUserExtractor currentUserExtractor;
    private final ProfileRepository profileRepository;

    @Transactional
    public Profile getOrCreateCurrentProfile(Jwt jwt) {
        UUID userId = currentUserExtractor.extract(jwt).userId();

        return profileRepository.findById(userId)
                .orElseGet(() -> createOrFindConcurrently(userId));
    }

    @Transactional
    public Profile requireActiveProfile(Jwt jwt) {
        Profile profile = getOrCreateCurrentProfile(jwt);
        if (profile.getMemberStatus() != MemberStatus.ACTIVE) {
            throw new MemberAccessDeniedException();
        }
        return profile;
    }

    private Profile createOrFindConcurrently(UUID userId) {
        try {
            profileRepository.insertIfAbsent(userId);
        } catch (DataAccessException exception) {
            // 실패한 트랜잭션을 계속 사용하지 않고 안전한 도메인 예외로 즉시 종료한다.
            throw new ProfileProvisioningException(exception);
        }

        return profileRepository.findById(userId)
                .orElseThrow(ProfileProvisioningException::new);
    }
}
