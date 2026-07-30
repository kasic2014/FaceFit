package com.facefit.backend.member.repository;

import com.facefit.backend.member.domain.Profile;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.UUID;

public interface ProfileRepository extends JpaRepository<Profile, UUID> {

    /**
     * 최초 요청이 동시에 실행되어도 PostgreSQL이 사용자별 프로필을 한 번만 생성한다.
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query(
            value = """
                    INSERT INTO profiles (user_id)
                    VALUES (:userId)
                    ON CONFLICT (user_id) DO NOTHING
                    """,
            nativeQuery = true
    )
    int insertIfAbsent(@Param("userId") UUID userId);

    /**
     * PostgreSQL이 상태 확인과 완료 일시 결정을 한 문장에서 처리한다.
     * 동시 완료 요청 중 하나만 상태를 바꾸며 이후 요청은 기존 완료 일시를 유지한다.
     */
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query(
            value = """
                    UPDATE profiles
                    SET onboarding_status = 'COMPLETED',
                        onboarding_completed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = :userId
                      AND member_status = 'ACTIVE'
                      AND onboarding_status IN ('NOT_STARTED', 'IN_PROGRESS')
                      AND onboarding_completed_at IS NULL
                    """,
            nativeQuery = true
    )
    int completeOnboardingIfEligible(@Param("userId") UUID userId);
}
