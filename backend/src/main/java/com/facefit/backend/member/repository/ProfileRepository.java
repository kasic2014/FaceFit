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
}
