package com.facefit.backend.interview.repository;

import com.facefit.backend.interview.domain.InterviewReport;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;
import java.util.UUID;

public interface InterviewReportRepository extends JpaRepository<InterviewReport, UUID> {

    boolean existsBySession_SessionId(UUID sessionId);

    Optional<InterviewReport> findBySession_SessionId(UUID sessionId);
}
