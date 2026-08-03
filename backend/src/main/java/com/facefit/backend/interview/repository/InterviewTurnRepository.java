package com.facefit.backend.interview.repository;

import com.facefit.backend.interview.domain.InterviewTurn;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface InterviewTurnRepository extends JpaRepository<InterviewTurn, UUID> {

    long countBySession_SessionId(UUID sessionId);

    List<InterviewTurn> findAllBySession_SessionIdOrderByQuestionOrder(UUID sessionId);

    @Query(
            value = """
                    SELECT t.*
                    FROM interview_turns t
                    WHERE t.session_id = :sessionId
                      AND NOT EXISTS (
                            SELECT 1
                            FROM interview_answers a
                            WHERE a.turn_id = t.turn_id
                              AND a.confirmed_at IS NOT NULL
                      )
                    ORDER BY t.question_order ASC
                    LIMIT 1
                    """,
            nativeQuery = true
    )
    Optional<InterviewTurn> findFirstUnanswered(@Param("sessionId") UUID sessionId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select t from InterviewTurn t
            where t.turnId = :turnId
              and t.session.sessionId = :sessionId
            """)
    Optional<InterviewTurn> findByIdAndSessionForUpdate(
            @Param("turnId") UUID turnId,
            @Param("sessionId") UUID sessionId
    );
}
