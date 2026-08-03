package com.facefit.backend.interview.repository;

import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.InterviewProcessingJob;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;

public interface InterviewProcessingJobRepository
        extends JpaRepository<InterviewProcessingJob, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select j from InterviewProcessingJob j where j.jobId = :jobId")
    Optional<InterviewProcessingJob> findByIdForUpdate(@Param("jobId") UUID jobId);

    Optional<InterviewProcessingJob>
    findFirstBySession_SessionIdAndTypeOrderByCreatedAtDesc(
            UUID sessionId,
            InterviewJobType type
    );

    @Query("""
            select j from InterviewProcessingJob j
            where j.session.sessionId = :sessionId
              and j.type = :type
              and j.status in :statuses
            """)
    Optional<InterviewProcessingJob> findActive(
            @Param("sessionId") UUID sessionId,
            @Param("type") InterviewJobType type,
            @Param("statuses") Set<InterviewJobStatus> statuses
    );

    boolean existsBySession_SessionIdAndTypeAndStatusIn(
            UUID sessionId,
            InterviewJobType type,
            Set<InterviewJobStatus> statuses
    );

    List<InterviewProcessingJob> findAllByAnswer_AnswerIdOrderByType(UUID answerId);

    Optional<InterviewProcessingJob> findByAnswer_AnswerIdAndType(
            UUID answerId,
            InterviewJobType type
    );

    List<InterviewProcessingJob> findAllBySession_SessionId(UUID sessionId);

    @Query("select j.session.sessionId from InterviewProcessingJob j where j.jobId = :jobId")
    Optional<UUID> findSessionId(@Param("jobId") UUID jobId);

    @Query(
            value = """
                    SELECT job_id
                    FROM interview_processing_jobs
                    WHERE (
                            job_status = 'QUEUED'
                            AND next_retry_at <= now()
                          )
                       OR (
                            job_status = 'PROCESSING'
                            AND locked_at <= now() - (:staleSeconds * interval '1 second')
                          )
                    ORDER BY next_retry_at ASC, created_at ASC
                    LIMIT :limit
                    """,
            nativeQuery = true
    )
    List<UUID> findDueJobIds(
            @Param("staleSeconds") int staleSeconds,
            @Param("limit") int limit
    );
}
