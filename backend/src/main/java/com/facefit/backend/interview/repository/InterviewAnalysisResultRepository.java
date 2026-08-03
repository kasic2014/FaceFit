package com.facefit.backend.interview.repository;

import com.facefit.backend.interview.domain.InterviewAnalysisResult;
import com.facefit.backend.interview.domain.InterviewJobType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface InterviewAnalysisResultRepository
        extends JpaRepository<InterviewAnalysisResult, UUID> {

    boolean existsBySourceJob_JobId(UUID jobId);

    Optional<InterviewAnalysisResult> findByAnswer_AnswerIdAndAnalysisType(
            UUID answerId,
            InterviewJobType analysisType
    );

    List<InterviewAnalysisResult>
    findAllBySession_SessionIdOrderByAnswer_Turn_QuestionOrderAscAnalysisTypeAsc(
            UUID sessionId
    );
}
