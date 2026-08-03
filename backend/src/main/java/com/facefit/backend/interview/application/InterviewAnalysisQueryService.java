package com.facefit.backend.interview.application;

import com.facefit.backend.common.exception.InterviewProgressException;
import com.facefit.backend.common.exception.InvalidInterviewSessionStateException;
import com.facefit.backend.common.exception.ResourceNotFoundException;
import com.facefit.backend.interview.api.AnalysisStageStatus;
import com.facefit.backend.interview.api.AnalysisStages;
import com.facefit.backend.interview.api.AnalysisStatus;
import com.facefit.backend.interview.api.InterviewAnalysisStatusResponse;
import com.facefit.backend.interview.api.InterviewReportData;
import com.facefit.backend.interview.api.InterviewReportResponse;
import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.InterviewProcessingJob;
import com.facefit.backend.interview.domain.InterviewReport;
import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.repository.InterviewAnswerRepository;
import com.facefit.backend.interview.repository.InterviewProcessingJobRepository;
import com.facefit.backend.interview.repository.InterviewReportRepository;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import com.facefit.backend.onboarding.application.OnboardingService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class InterviewAnalysisQueryService {

    private static final int EXPECTED_ANSWERS = 10;
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

    private final OnboardingService onboardingService;
    private final InterviewSessionRepository sessionRepository;
    private final InterviewAnswerRepository answerRepository;
    private final InterviewProcessingJobRepository jobRepository;
    private final InterviewReportRepository reportRepository;

    @Transactional(readOnly = true)
    public InterviewAnalysisStatusResponse analysisStatus(Jwt jwt, UUID sessionId) {
        UUID userId = onboardingService.requireCompletedOnboarding(jwt).getUserId();
        InterviewSession session = sessionRepository
                .findOwnedById(sessionId, userId)
                .orElseThrow(ResourceNotFoundException::new);
        requireAnalysisReadable(session);

        Set<InterviewJobType> requiredTypes = analysisTypes(session);
        int expectedJobs = EXPECTED_ANSWERS * requiredTypes.size();
        List<InterviewProcessingJob> jobs = analysisJobs(sessionId, requiredTypes);
        AnalysisStageStatus stt = stage(jobs, InterviewJobType.STT, EXPECTED_ANSWERS);
        AnalysisStageStatus cv = stage(jobs, InterviewJobType.CV, EXPECTED_ANSWERS);
        AnalysisStageStatus voice = stage(
                jobs,
                InterviewJobType.VOICE,
                session.isVoiceAnalysisEnabled() ? EXPECTED_ANSWERS : 0
        );
        AnalysisStageStatus content = stage(jobs, InterviewJobType.CONTENT, EXPECTED_ANSWERS);
        int succeeded = (int) jobs.stream()
                .filter(job -> job.getStatus() == InterviewJobStatus.SUCCEEDED)
                .count();
        int completedAnswers = (int) answerRepository
                .findAllBySession_SessionIdOrderByTurn_QuestionOrder(sessionId)
                .stream()
                .filter(answer -> jobs.stream()
                        .filter(job -> job.getAnswer() != null
                                && job.getAnswer().getAnswerId()
                                .equals(answer.getAnswerId()))
                        .filter(job -> requiredTypes.contains(job.getType()))
                        .allMatch(job -> job.getStatus() == InterviewJobStatus.SUCCEEDED))
                .filter(answer -> jobs.stream()
                        .filter(job -> job.getAnswer() != null
                                && job.getAnswer().getAnswerId()
                                .equals(answer.getAnswerId()))
                        .filter(job -> requiredTypes.contains(job.getType()))
                        .count() == requiredTypes.size())
                .count();
        int failedAnswers = (int) jobs.stream()
                .filter(job -> job.getAnswer() != null)
                .filter(job -> job.getStatus() == InterviewJobStatus.FAILED)
                .map(job -> job.getAnswer().getAnswerId())
                .distinct()
                .count();
        boolean failed = failedAnswers > 0;
        AnalysisStatus status = failed
                ? AnalysisStatus.FAILED
                : succeeded == expectedJobs
                ? AnalysisStatus.SUCCEEDED
                : jobs.stream().noneMatch(job ->
                        job.getStatus() == InterviewJobStatus.PROCESSING
                                || job.getStatus() == InterviewJobStatus.SUCCEEDED)
                ? AnalysisStatus.WAITING
                : AnalysisStatus.PROCESSING;
        return new InterviewAnalysisStatusResponse(
                sessionId,
                session.getStatus(),
                status,
                (int) answerRepository
                        .countBySession_SessionIdAndConfirmedAtIsNotNull(sessionId),
                completedAnswers,
                failedAnswers,
                (int) Math.round(succeeded * 100.0 / expectedJobs),
                new AnalysisStages(stt, cv, voice, content),
                reportStatus(sessionId, failed),
                false,
                failed ? "ANSWER_ANALYSIS_FAILED" : null
        );
    }

    @Transactional(readOnly = true)
    public IdempotentResult<InterviewReportResponse> report(
            Jwt jwt,
            UUID sessionId
    ) {
        UUID userId = onboardingService.requireCompletedOnboarding(jwt).getUserId();
        InterviewSession session = sessionRepository
                .findOwnedById(sessionId, userId)
                .orElseThrow(ResourceNotFoundException::new);
        if (session.getStatus() == InterviewSessionStatus.INTERRUPTED) {
            throw new InterviewProgressException(
                    HttpStatus.CONFLICT,
                    "REPORT_NOT_AVAILABLE",
                    "중단된 면접에는 리포트를 제공하지 않습니다."
            );
        }
        requireAnalysisReadable(session);

        InterviewReport report = reportRepository
                .findBySession_SessionId(sessionId)
                .orElse(null);
        if (report != null && session.getStatus() == InterviewSessionStatus.COMPLETED) {
            return new IdempotentResult<>(
                    HttpStatus.OK.value(),
                    response(session, "SUCCEEDED", reportData(report))
            );
        }

        List<InterviewProcessingJob> jobs = analysisJobs(
                sessionId,
                analysisTypes(session)
        );
        if (jobs.stream().anyMatch(job -> job.getStatus() == InterviewJobStatus.FAILED)) {
            throw new InterviewProgressException(
                    HttpStatus.CONFLICT,
                    "REPORT_BLOCKED_BY_ANALYSIS_FAILURE",
                    "필수 답변 분석 실패로 리포트를 생성할 수 없습니다.",
                    false
            );
        }
        InterviewProcessingJob reportJob = jobRepository
                .findFirstBySession_SessionIdAndTypeOrderByCreatedAtDesc(
                        sessionId,
                        InterviewJobType.REPORT_GENERATION
                )
                .orElse(null);
        if (reportJob != null && reportJob.getStatus() == InterviewJobStatus.FAILED) {
            throw new InterviewProgressException(
                    HttpStatus.SERVICE_UNAVAILABLE,
                    "REPORT_GENERATION_FAILED",
                    "면접 리포트를 생성하지 못했습니다.",
                    Boolean.TRUE.equals(reportJob.getFailureRetryable())
            );
        }
        String status = reportJob == null
                ? "WAITING_FOR_ANALYSIS"
                : "PROCESSING";
        return new IdempotentResult<>(
                HttpStatus.ACCEPTED.value(),
                response(session, status, null)
        );
    }

    private void requireAnalysisReadable(InterviewSession session) {
        if (!EnumSet.of(
                InterviewSessionStatus.INTERVIEW_COMPLETED,
                InterviewSessionStatus.ANALYZING,
                InterviewSessionStatus.COMPLETED
        ).contains(session.getStatus())) {
            throw new InvalidInterviewSessionStateException();
        }
    }

    private List<InterviewProcessingJob> analysisJobs(
            UUID sessionId,
            Set<InterviewJobType> requiredTypes
    ) {
        return jobRepository.findAllBySession_SessionId(sessionId).stream()
                .filter(job -> requiredTypes.contains(job.getType()))
                .toList();
    }

    private AnalysisStageStatus stage(
            List<InterviewProcessingJob> jobs,
            InterviewJobType type,
            int total
    ) {
        List<InterviewProcessingJob> stageJobs = jobs.stream()
                .filter(job -> job.getType() == type)
                .toList();
        return new AnalysisStageStatus(
                total,
                count(stageJobs, InterviewJobStatus.QUEUED),
                count(stageJobs, InterviewJobStatus.PROCESSING),
                count(stageJobs, InterviewJobStatus.SUCCEEDED),
                count(stageJobs, InterviewJobStatus.FAILED)
        );
    }

    private Set<InterviewJobType> analysisTypes(InterviewSession session) {
        return session.isVoiceAnalysisEnabled()
                ? ANALYSIS_TYPES_WITH_VOICE
                : ANALYSIS_TYPES_WITHOUT_VOICE;
    }

    private int count(
            List<InterviewProcessingJob> jobs,
            InterviewJobStatus status
    ) {
        return (int) jobs.stream()
                .filter(job -> job.getStatus() == status)
                .count();
    }

    private String reportStatus(UUID sessionId, boolean analysisFailed) {
        if (reportRepository.existsBySession_SessionId(sessionId)) {
            return "SUCCEEDED";
        }
        if (analysisFailed) {
            return "BLOCKED_BY_ANALYSIS_FAILURE";
        }
        return jobRepository
                .findFirstBySession_SessionIdAndTypeOrderByCreatedAtDesc(
                        sessionId,
                        InterviewJobType.REPORT_GENERATION
                )
                .map(job -> job.getStatus() == InterviewJobStatus.FAILED
                        ? "FAILED"
                        : "PROCESSING")
                .orElse("WAITING_FOR_ANALYSIS");
    }

    private InterviewReportResponse response(
            InterviewSession session,
            String status,
            InterviewReportData report
    ) {
        return new InterviewReportResponse(
                session.getSessionId(),
                session.getStatus(),
                status,
                report
        );
    }

    private InterviewReportData reportData(InterviewReport report) {
        return new InterviewReportData(
                report.getReportId(),
                report.getSchemaVersion(),
                report.getOverallScore(),
                new InterviewReportData.ReportScores(
                        report.getGazeScore(),
                        report.getPostureScore(),
                        report.getSpeechScore(),
                        report.getContentScore()
                ),
                report.getStrengths(),
                report.getImprovements(),
                report.getQuestionFeedback(),
                report.getGeneratedAt()
        );
    }
}
