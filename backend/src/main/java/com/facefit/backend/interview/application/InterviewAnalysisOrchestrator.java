package com.facefit.backend.interview.application;

import com.facefit.backend.interview.domain.InterviewAnswer;
import com.facefit.backend.interview.domain.InterviewCompletionType;
import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.InterviewProcessingJob;
import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.repository.InterviewAnswerRepository;
import com.facefit.backend.interview.repository.InterviewProcessingJobRepository;
import com.facefit.backend.interview.repository.InterviewReportRepository;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import com.facefit.backend.interview.repository.InterviewTurnRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class InterviewAnalysisOrchestrator {

    private static final int REQUIRED_ANSWERS = 10;
    private static final Set<InterviewJobType> ANALYSIS_TYPES_WITH_VOICE = EnumSet.of(
            InterviewJobType.STT,
            InterviewJobType.CV,
            InterviewJobType.VOICE,
            InterviewJobType.CONTENT
    );
    private static final Set<InterviewJobType> ANALYSIS_TYPES_WITHOUT_VOICE = EnumSet.of(
            InterviewJobType.STT,
            InterviewJobType.CV,
            InterviewJobType.CONTENT
    );

    private final InterviewSessionRepository sessionRepository;
    private final InterviewTurnRepository turnRepository;
    private final InterviewAnswerRepository answerRepository;
    private final InterviewProcessingJobRepository jobRepository;
    private final InterviewReportRepository reportRepository;
    private final ApplicationEventPublisher eventPublisher;

    @Transactional
    public void orchestrate(UUID sessionId) {
        InterviewSession session = sessionRepository
                .findByIdForUpdate(sessionId)
                .orElse(null);
        if (session == null
                || session.getCompletionType() != InterviewCompletionType.NORMAL
                || session.getStatus() == InterviewSessionStatus.INTERRUPTED
                || session.getStatus() == InterviewSessionStatus.COMPLETED) {
            return;
        }
        if (session.getStatus() != InterviewSessionStatus.INTERVIEW_COMPLETED
                && session.getStatus() != InterviewSessionStatus.ANALYZING) {
            return;
        }

        List<InterviewAnswer> answers = answerRepository
                .findAllBySession_SessionIdOrderByTurn_QuestionOrder(sessionId)
                .stream()
                .filter(InterviewAnswer::isConfirmed)
                .toList();
        Set<InterviewJobType> requiredTypes = analysisTypes(session);
        List<InterviewProcessingJob> analysisJobs = jobRepository
                .findAllBySession_SessionId(sessionId)
                .stream()
                .filter(job -> requiredTypes.contains(job.getType()))
                .toList();
        if (!hasCompleteInput(sessionId, answers, analysisJobs, requiredTypes)) {
            return;
        }

        if (session.getStatus() == InterviewSessionStatus.INTERVIEW_COMPLETED) {
            session.beginAnalysis(OffsetDateTime.now());
            sessionRepository.saveAndFlush(session);
        }

        boolean hasFailure = analysisJobs.stream()
                .anyMatch(job -> job.getStatus() == InterviewJobStatus.FAILED);
        boolean allSucceeded = analysisJobs.stream()
                .allMatch(job -> job.getStatus() == InterviewJobStatus.SUCCEEDED);
        if (hasFailure || !allSucceeded || reportRepository.existsBySession_SessionId(sessionId)) {
            return;
        }
        if (jobRepository.findFirstBySession_SessionIdAndTypeOrderByCreatedAtDesc(
                sessionId,
                InterviewJobType.REPORT_GENERATION
        ).isPresent()) {
            return;
        }

        UUID jobId = UUID.randomUUID();
        jobRepository.saveAndFlush(
                InterviewProcessingJob.reportGeneration(jobId, session)
        );
        eventPublisher.publishEvent(new ReportGenerationRequestedEvent(jobId));
    }

    private boolean hasCompleteInput(
            UUID sessionId,
            List<InterviewAnswer> answers,
            List<InterviewProcessingJob> jobs,
            Set<InterviewJobType> requiredTypes
    ) {
        if (turnRepository.countBySession_SessionId(sessionId) != REQUIRED_ANSWERS
                || answers.size() != REQUIRED_ANSWERS
                || jobs.size() != REQUIRED_ANSWERS * requiredTypes.size()) {
            return false;
        }
        return answers.stream().allMatch(answer -> {
            Set<InterviewJobType> types = jobs.stream()
                    .filter(job -> job.getAnswer() != null
                            && job.getAnswer().getAnswerId().equals(answer.getAnswerId()))
                    .map(InterviewProcessingJob::getType)
                    .collect(Collectors.toSet());
            return types.equals(requiredTypes);
        });
    }

    private Set<InterviewJobType> analysisTypes(InterviewSession session) {
        return session.isVoiceAnalysisEnabled()
                ? ANALYSIS_TYPES_WITH_VOICE
                : ANALYSIS_TYPES_WITHOUT_VOICE;
    }
}
