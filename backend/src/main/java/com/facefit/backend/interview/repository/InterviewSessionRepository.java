package com.facefit.backend.interview.repository;

import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;
import java.util.List;
import java.util.Set;
import java.util.UUID;

public interface InterviewSessionRepository extends JpaRepository<InterviewSession, UUID> {

    boolean existsBySessionIdAndProfile_UserId(UUID sessionId, UUID userId);

    @Query("""
            select s from InterviewSession s
            where s.sessionId = :sessionId
              and s.profile.userId = :userId
            """)
    Optional<InterviewSession> findOwnedById(
            @Param("sessionId") UUID sessionId,
            @Param("userId") UUID userId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select s from InterviewSession s
            where s.sessionId = :sessionId
              and s.profile.userId = :userId
            """)
    Optional<InterviewSession> findOwnedByIdForUpdate(
            @Param("sessionId") UUID sessionId,
            @Param("userId") UUID userId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from InterviewSession s where s.sessionId = :sessionId")
    Optional<InterviewSession> findByIdForUpdate(@Param("sessionId") UUID sessionId);

    @Query("""
            select (count(s) > 0) from InterviewSession s
            where s.profile.userId = :userId
              and s.status in :statuses
              and (
                    s.resumeDocument.documentId = :documentId
                    or s.coverLetterDocument.documentId = :documentId
              )
            """)
    boolean existsNonTerminalReferenceToDocument(
            @Param("userId") UUID userId,
            @Param("documentId") UUID documentId,
            @Param("statuses") Set<InterviewSessionStatus> statuses
    );

    @Query("""
            select (count(s) > 0) from InterviewSession s
            where s.profile.userId = :userId
              and s.status in :statuses
              and s.jobPosting.jobPostingId = :jobPostingId
            """)
    boolean existsNonTerminalReferenceToJobPosting(
            @Param("userId") UUID userId,
            @Param("jobPostingId") UUID jobPostingId,
            @Param("statuses") Set<InterviewSessionStatus> statuses
    );

    @Query(
            value = """
                    SELECT session_id
                    FROM interview_sessions
                    WHERE session_status IN ('INTERVIEW_COMPLETED', 'ANALYZING')
                      AND completion_type = 'NORMAL'
                    ORDER BY updated_at ASC, session_id ASC
                    LIMIT :limit
                    """,
            nativeQuery = true
    )
    List<UUID> findAnalysisCandidateIds(@Param("limit") int limit);
}
