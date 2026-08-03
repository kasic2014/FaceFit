package com.facefit.backend.jobposting.repository;

import com.facefit.backend.jobposting.domain.JobPosting;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface JobPostingRepository extends JpaRepository<JobPosting, UUID> {

    @Query("""
            select j from JobPosting j
            where j.profile.userId = :userId
              and j.deletedAt is null
              and (:status is null or j.processingStatus = :status)
            """)
    Page<JobPosting> findActiveByOwner(
            @Param("userId") UUID userId,
            @Param("status") JobPostingProcessingStatus status,
            Pageable pageable
    );

    Optional<JobPosting> findByJobPostingIdAndProfile_UserIdAndDeletedAtIsNull(
            UUID jobPostingId,
            UUID userId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
            select j from JobPosting j
            where j.jobPostingId = :jobPostingId
              and j.profile.userId = :userId
              and j.deletedAt is null
            """)
    Optional<JobPosting> findActiveOwnedByIdForUpdate(
            @Param("jobPostingId") UUID jobPostingId,
            @Param("userId") UUID userId
    );

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select j from JobPosting j where j.jobPostingId = :jobPostingId")
    Optional<JobPosting> findByIdForUpdate(@Param("jobPostingId") UUID jobPostingId);

    @Query("""
            select j.jobPostingId from JobPosting j
            where j.processingStatus = com.facefit.backend.jobposting.domain.JobPostingProcessingStatus.PROCESSING
              and j.deletedAt is null
              and j.processingAttemptCount < :maxAttempts
              and (j.processingStartedAt is null or j.processingStartedAt < :staleBefore)
            order by j.createdAt asc, j.jobPostingId asc
            """)
    List<UUID> findRecoverableIds(
            @Param("staleBefore") OffsetDateTime staleBefore,
            @Param("maxAttempts") int maxAttempts,
            Pageable pageable
    );
}
