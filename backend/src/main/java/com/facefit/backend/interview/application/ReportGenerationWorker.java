package com.facefit.backend.interview.application;

import com.facefit.backend.interview.domain.InterviewCompletionType;
import com.facefit.backend.interview.domain.InterviewAnswer;
import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewProcessingJob;
import com.facefit.backend.interview.domain.InterviewReport;
import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.repository.InterviewAnalysisResultRepository;
import com.facefit.backend.interview.repository.InterviewAnswerRepository;
import com.facefit.backend.interview.repository.InterviewProcessingJobRepository;
import com.facefit.backend.interview.repository.InterviewReportRepository;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class ReportGenerationWorker {

    private final InterviewSessionRepository sessionRepository;
    private final InterviewProcessingJobRepository jobRepository;
    private final InterviewAnswerRepository answerRepository;
    private final InterviewAnalysisResultRepository analysisResultRepository;
    private final InterviewReportRepository reportRepository;
    private final InterviewReportAggregator aggregator;
    private final TransactionTemplate transactionTemplate;

    @Value("${facefit.interview.processing.report-timeout-seconds:60}")
    private long reportTimeoutSeconds;

    public void process(UUID jobId) {
        Claim claim = claim(jobId);
        if (claim == null) {
            return;
        }
        try {
            finalizeReport(claim);
        } catch (IllegalArgumentException exception) {
            fail(claim, "REPORT_INPUT_INVALID", false);
        }
    }

    private Claim claim(UUID jobId) {
        UUID sessionId = jobRepository.findSessionId(jobId).orElse(null);
        if (sessionId == null) {
            return null;
        }
        return transactionTemplate.execute(status -> {
            InterviewSession session = sessionRepository
                    .findByIdForUpdate(sessionId)
                    .orElse(null);
            InterviewProcessingJob job = jobRepository
                    .findByIdForUpdate(jobId)
                    .orElse(null);
            if (session == null
                    || job == null
                    || job.getType() != InterviewJobType.REPORT_GENERATION
                    || job.getAnswer() != null
                    || session.getStatus() != InterviewSessionStatus.ANALYZING
                    || session.getCompletionType() != InterviewCompletionType.NORMAL) {
                return null;
            }
            OffsetDateTime now = OffsetDateTime.now();
            Duration staleAfter = Duration.ofSeconds(reportTimeoutSeconds);
            if (job.failExhaustedStaleClaim(now, staleAfter)) {
                jobRepository.saveAndFlush(job);
                return null;
            }
            UUID token = UUID.randomUUID();
            if (!job.claim(token, now, staleAfter)) {
                return null;
            }
            jobRepository.saveAndFlush(job);
            return new Claim(jobId, sessionId, token);
        });
    }

    private void finalizeReport(Claim claim) {
        transactionTemplate.executeWithoutResult(status -> {
            InterviewSession session = sessionRepository
                    .findByIdForUpdate(claim.sessionId())
                    .orElse(null);
            InterviewProcessingJob job = jobRepository
                    .findByIdForUpdate(claim.jobId())
                    .orElse(null);
            if (session == null
                    || job == null
                    || !job.isOwnedBy(claim.workerToken())
                    || session.getStatus() != InterviewSessionStatus.ANALYZING
                    || session.getCompletionType() != InterviewCompletionType.NORMAL) {
                return;
            }
            if (reportRepository.existsBySession_SessionId(claim.sessionId())) {
                return;
            }
            List<InterviewAnswer> answers = answerRepository
                    .findAllBySession_SessionIdOrderByTurn_QuestionOrder(
                            claim.sessionId()
                    )
                    .stream()
                    .filter(InterviewAnswer::isConfirmed)
                    .toList();
            Set<InterviewJobType> requiredTypes = session.isVoiceAnalysisEnabled()
                    ? EnumSet.of(
                    InterviewJobType.STT,
                    InterviewJobType.CV,
                    InterviewJobType.VOICE,
                    InterviewJobType.CONTENT
            )
                    : EnumSet.of(
                    InterviewJobType.STT,
                    InterviewJobType.CV,
                    InterviewJobType.CONTENT
            );
            boolean allAnalysisSucceeded = jobRepository
                    .findAllBySession_SessionId(claim.sessionId())
                    .stream()
                    .filter(candidate -> requiredTypes.contains(candidate.getType()))
                    .filter(candidate ->
                            candidate.getStatus() == InterviewJobStatus.SUCCEEDED)
                    .count() == 10L * requiredTypes.size();
            boolean allTranscriptsReady = answers.size() == 10
                    && answers.stream().allMatch(answer ->
                    answer.getTranscript() != null
                            && !answer.getTranscript().isBlank()
                            && answer.getTranscriptSchemaVersion() != null);
            if (!allAnalysisSucceeded || !allTranscriptsReady) {
                throw new IllegalArgumentException("필수 분석이 완료되지 않았습니다.");
            }
            AggregatedReport aggregated = aggregator.aggregate(
                    answers,
                    analysisResultRepository
                            .findAllBySession_SessionIdOrderByAnswer_Turn_QuestionOrderAscAnalysisTypeAsc(
                                    claim.sessionId()
                            ),
                    session.isVoiceAnalysisEnabled()
            );
            OffsetDateTime now = OffsetDateTime.now();
            reportRepository.saveAndFlush(InterviewReport.create(
                    UUID.randomUUID(),
                    session,
                    aggregated.schemaVersion(),
                    aggregated.inputHash(),
                    aggregated.overallScore(),
                    aggregated.gazeScore(),
                    aggregated.postureScore(),
                    aggregated.speechScore(),
                    aggregated.contentScore(),
                    aggregated.strengths(),
                    aggregated.improvements(),
                    aggregated.questionFeedback(),
                    now
            ));
            session.completeAnalysis(now);
            sessionRepository.saveAndFlush(session);
            job.succeed(claim.workerToken(), null, now);
            jobRepository.saveAndFlush(job);
        });
    }

    private void fail(Claim claim, String code, boolean retryable) {
        transactionTemplate.executeWithoutResult(status -> {
            InterviewSession session = sessionRepository
                    .findByIdForUpdate(claim.sessionId())
                    .orElse(null);
            InterviewProcessingJob job = jobRepository
                    .findByIdForUpdate(claim.jobId())
                    .orElse(null);
            if (session == null || job == null || !job.isOwnedBy(claim.workerToken())) {
                return;
            }
            OffsetDateTime now = OffsetDateTime.now();
            if (retryable) {
                job.retry(claim.workerToken(), code, now);
            } else {
                job.fail(claim.workerToken(), code, false, now);
            }
            jobRepository.saveAndFlush(job);
        });
    }

    private record Claim(UUID jobId, UUID sessionId, UUID workerToken) {
    }
}
