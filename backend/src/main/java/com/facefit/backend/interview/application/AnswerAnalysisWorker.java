package com.facefit.backend.interview.application;

import com.facefit.backend.interview.domain.InterviewAnalysisResult;
import com.facefit.backend.interview.domain.InterviewAnswer;
import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.InterviewProcessingJob;
import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.integration.AnalysisResult;
import com.facefit.backend.interview.integration.AnswerAnalysisRequest;
import com.facefit.backend.interview.integration.ContentAnalysisPort;
import com.facefit.backend.interview.integration.CvAnalysisPort;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.integration.SttPort;
import com.facefit.backend.interview.integration.SttResult;
import com.facefit.backend.interview.integration.VoiceAnalysisPort;
import com.facefit.backend.interview.repository.InterviewAnswerRepository;
import com.facefit.backend.interview.repository.InterviewAnalysisResultRepository;
import com.facefit.backend.interview.repository.InterviewProcessingJobRepository;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class AnswerAnalysisWorker {

    private final InterviewProcessingJobRepository jobRepository;
    private final InterviewSessionRepository sessionRepository;
    private final InterviewAnswerRepository answerRepository;
    private final InterviewAnalysisResultRepository analysisResultRepository;
    private final ObjectProvider<SttPort> sttPort;
    private final ObjectProvider<CvAnalysisPort> cvPort;
    private final ObjectProvider<VoiceAnalysisPort> voicePort;
    private final ObjectProvider<ContentAnalysisPort> contentPort;
    private final ExternalCallExecutor externalCallExecutor;
    private final TransactionTemplate transactionTemplate;
    private final AnalysisResultNormalizer resultNormalizer;
    private final InterviewAnalysisOrchestrator orchestrator;

    @Value("${facefit.interview.processing.stt-timeout-seconds:120}")
    private long sttTimeoutSeconds;

    @Value("${facefit.interview.processing.analysis-timeout-seconds:60}")
    private long analysisTimeoutSeconds;

    public void process(UUID jobId) {
        UUID sessionId = jobRepository.findSessionId(jobId).orElse(null);
        Claim claim = claim(jobId);
        if (claim == null) {
            if (sessionId != null) {
                orchestrator.orchestrate(sessionId);
            }
            return;
        }
        switch (claim.type()) {
            case STT -> runStt(claim);
            case CV -> runAnalysis(
                    claim,
                    cvPort.getIfAvailable(),
                    "CV_ADAPTER_NOT_CONFIGURED"
            );
            case VOICE -> runAnalysis(
                    claim,
                    voicePort.getIfAvailable(),
                    "VOICE_ADAPTER_NOT_CONFIGURED"
            );
            case CONTENT -> runContent(claim);
            case QUESTION_GENERATION, REPORT_GENERATION ->
                    fail(claim, "INVALID_ANSWER_JOB_TYPE", false);
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
                    || job.getType() == InterviewJobType.QUESTION_GENERATION
                    || job.getAnswer() == null) {
                return null;
            }
            InterviewAnswer answer = answerRepository
                    .findByIdForUpdate(job.getAnswer().getAnswerId())
                    .orElse(null);
            if (answer == null || !answer.isConfirmed()) {
                return null;
            }
            if (job.getType() == InterviewJobType.CONTENT) {
                InterviewProcessingJob sttJob = jobRepository
                        .findByAnswer_AnswerIdAndType(
                                answer.getAnswerId(),
                                InterviewJobType.STT
                        )
                        .orElse(null);
                if (sttJob == null
                        || sttJob.getStatus() == InterviewJobStatus.FAILED) {
                    failDependency(job, answer);
                    return null;
                }
                if (sttJob.getStatus() != InterviewJobStatus.SUCCEEDED) {
                    return null;
                }
                if (answer.getTranscript() == null
                        || answer.getTranscript().isBlank()) {
                    failDependency(job, answer);
                    return null;
                }
            }
            UUID token = UUID.randomUUID();
            long timeout = job.getType() == InterviewJobType.STT
                    ? sttTimeoutSeconds
                    : analysisTimeoutSeconds;
            OffsetDateTime now = OffsetDateTime.now();
            Duration staleAfter = Duration.ofSeconds(timeout);
            if (job.failExhaustedStaleClaim(now, staleAfter)) {
                jobRepository.saveAndFlush(job);
                refreshAnswerStatus(answer);
                return null;
            }
            if (!job.claim(
                    token,
                    now,
                    staleAfter
            )) {
                return null;
            }
            answer.markProcessing();
            jobRepository.saveAndFlush(job);
            answerRepository.saveAndFlush(answer);
            return new Claim(
                    jobId,
                    sessionId,
                    answer.getAnswerId(),
                    token,
                    job.getType(),
                    new AnswerAnalysisRequest(
                            answer.getAnswerId(),
                            sessionId,
                            answer.getTurn().getTurnId(),
                            answer.getTurn().getQuestionText(),
                            answer.getStorageProvider(),
                            answer.getStorageBucket(),
                            answer.getStoragePath(),
                            answer.getMimeType(),
                            answer.getFileSizeBytes(),
                            answer.getRecordedDurationSeconds(),
                            answer.getDetectedDurationMillis(),
                            answer.getTranscript()
                    )
            );
        });
    }

    private void runStt(Claim claim) {
        SttPort port = sttPort.getIfAvailable();
        if (port == null) {
            fail(claim, "STT_ADAPTER_NOT_CONFIGURED", false);
            return;
        }
        PortResult<SttResult> result = externalCallExecutor.call(
                () -> port.transcribe(claim.request()),
                Duration.ofSeconds(sttTimeoutSeconds)
        );
        if (result instanceof PortResult.Success<?> success
                && success.value() instanceof SttResult stt) {
            String transcript = normalizedTranscript(stt.transcript());
            String schemaVersion = normalizedSchemaVersion(stt.schemaVersion());
            if (transcript == null || schemaVersion == null) {
                fail(claim, "STT_RESPONSE_INVALID", true);
            } else {
                succeedStt(claim, schemaVersion, transcript);
            }
        } else {
            handleFailureResult(claim, result, "STT_RESPONSE_INVALID");
        }
    }

    private void runAnalysis(
            Claim claim,
            Object port,
            String notConfiguredCode
    ) {
        if (port == null) {
            fail(claim, notConfiguredCode, false);
            return;
        }
        PortResult<AnalysisResult> result = externalCallExecutor.call(
                () -> {
                    if (port instanceof CvAnalysisPort cv) {
                        return cv.analyze(claim.request());
                    }
                    return ((VoiceAnalysisPort) port).analyze(claim.request());
                },
                Duration.ofSeconds(analysisTimeoutSeconds)
        );
        handleAnalysisResult(claim, result);
    }

    private void runContent(Claim claim) {
        ContentAnalysisPort port = contentPort.getIfAvailable();
        if (port == null) {
            fail(claim, "CONTENT_ADAPTER_NOT_CONFIGURED", false);
            return;
        }
        if (claim.request().transcript() == null
                || claim.request().transcript().isBlank()) {
            fail(claim, "STT_RESULT_NOT_READY", true);
            return;
        }
        PortResult<AnalysisResult> result = externalCallExecutor.call(
                () -> port.analyze(claim.request()),
                Duration.ofSeconds(analysisTimeoutSeconds)
        );
        handleAnalysisResult(claim, result);
    }

    private void handleAnalysisResult(
            Claim claim,
            PortResult<AnalysisResult> result
    ) {
        if (result instanceof PortResult.Success<?> success
                && success.value() instanceof AnalysisResult analysis) {
            NormalizedAnalysisResult normalized = resultNormalizer.normalize(
                    claim.type(),
                    analysis
            );
            if (normalized == null) {
                fail(claim, "ANALYSIS_RESPONSE_INVALID", true);
            } else {
                succeedAnalysis(claim, normalized);
            }
        } else {
            handleFailureResult(claim, result, "ANALYSIS_RESPONSE_INVALID");
        }
    }

    private void handleFailureResult(
            Claim claim,
            PortResult<?> result,
            String invalidResponseCode
    ) {
        if (result instanceof PortResult.RetryableFailure<?> failure) {
            fail(claim, safeCode(failure.errorCode()), true);
        } else if (result instanceof PortResult.PermanentFailure<?> failure) {
            fail(claim, safeCode(failure.errorCode()), false);
        } else {
            fail(claim, invalidResponseCode, true);
        }
    }

    private void succeedStt(
            Claim claim,
            String schemaVersion,
            String transcript
    ) {
        transactionTemplate.executeWithoutResult(status -> {
            InterviewSession session = sessionRepository
                    .findByIdForUpdate(claim.sessionId())
                    .orElse(null);
            InterviewProcessingJob job = jobRepository
                    .findByIdForUpdate(claim.jobId())
                    .orElse(null);
            InterviewAnswer answer = answerRepository
                    .findByIdForUpdate(claim.answerId())
                    .orElse(null);
            if (session == null
                    || job == null
                    || answer == null
                    || !job.isOwnedBy(claim.workerToken())) {
                return;
            }
            answer.attachTranscript(schemaVersion, transcript);
            job.succeed(claim.workerToken(), null, OffsetDateTime.now());
            jobRepository.saveAndFlush(job);
            refreshAnswerStatus(answer);
        });
        orchestrator.orchestrate(claim.sessionId());
    }

    private void succeedAnalysis(
            Claim claim,
            NormalizedAnalysisResult normalized
    ) {
        transactionTemplate.executeWithoutResult(status -> {
            InterviewSession session = sessionRepository
                    .findByIdForUpdate(claim.sessionId())
                    .orElse(null);
            InterviewProcessingJob job = jobRepository
                    .findByIdForUpdate(claim.jobId())
                    .orElse(null);
            InterviewAnswer answer = answerRepository
                    .findByIdForUpdate(claim.answerId())
                    .orElse(null);
            if (session == null
                    || job == null
                    || answer == null
                    || !job.isOwnedBy(claim.workerToken())
                    || analysisResultRepository.existsBySourceJob_JobId(job.getJobId())) {
                return;
            }
            analysisResultRepository.saveAndFlush(
                    InterviewAnalysisResult.create(
                            UUID.randomUUID(),
                            session,
                            answer,
                            job,
                            claim.type(),
                            normalized.schemaVersion(),
                            normalized.gazeScore(),
                            normalized.postureScore(),
                            normalized.speechScore(),
                            normalized.contentScore(),
                            normalized.publicFeedback()
                    )
            );
            job.succeed(claim.workerToken(), null, OffsetDateTime.now());
            jobRepository.saveAndFlush(job);
            refreshAnswerStatus(answer);
        });
        orchestrator.orchestrate(claim.sessionId());
    }

    private void fail(Claim claim, String code, boolean retryable) {
        transactionTemplate.executeWithoutResult(status -> {
            InterviewSession session = sessionRepository
                    .findByIdForUpdate(claim.sessionId())
                    .orElse(null);
            InterviewProcessingJob job = jobRepository
                    .findByIdForUpdate(claim.jobId())
                    .orElse(null);
            InterviewAnswer answer = answerRepository
                    .findByIdForUpdate(claim.answerId())
                    .orElse(null);
            if (session == null
                    || job == null
                    || answer == null
                    || !job.isOwnedBy(claim.workerToken())) {
                return;
            }
            if (retryable) {
                job.retry(claim.workerToken(), safeCode(code), OffsetDateTime.now());
            } else {
                job.fail(
                        claim.workerToken(),
                        safeCode(code),
                        false,
                        OffsetDateTime.now()
                );
            }
            jobRepository.saveAndFlush(job);
            refreshAnswerStatus(answer);
        });
        orchestrator.orchestrate(claim.sessionId());
    }

    private void failDependency(
            InterviewProcessingJob job,
            InterviewAnswer answer
    ) {
        UUID token = UUID.randomUUID();
        OffsetDateTime now = OffsetDateTime.now();
        if (job.claim(token, now, Duration.ofSeconds(analysisTimeoutSeconds))) {
            job.fail(token, "DEPENDENCY_FAILED", false, now);
            jobRepository.saveAndFlush(job);
            refreshAnswerStatus(answer);
        }
    }

    private void refreshAnswerStatus(InterviewAnswer answer) {
        List<InterviewProcessingJob> jobs = jobRepository
                .findAllByAnswer_AnswerIdOrderByType(answer.getAnswerId());
        boolean allSucceeded = jobs.size() == 4
                && jobs.stream().allMatch(
                        job -> job.getStatus() == InterviewJobStatus.SUCCEEDED
                );
        boolean anyActive = jobs.stream().anyMatch(
                job -> job.getStatus() == InterviewJobStatus.QUEUED
                        || job.getStatus() == InterviewJobStatus.PROCESSING
        );
        boolean anyFailed = jobs.stream().anyMatch(
                job -> job.getStatus() == InterviewJobStatus.FAILED
        );
        answer.updateProcessingOutcome(allSucceeded, anyActive, anyFailed);
        answerRepository.saveAndFlush(answer);
    }

    private String normalizedTranscript(String transcript) {
        if (transcript == null) {
            return null;
        }
        String normalized = transcript.strip();
        if (normalized.isBlank()
                || normalized.codePointCount(0, normalized.length()) > 100_000) {
            return null;
        }
        return normalized;
    }

    private String normalizedSchemaVersion(String schemaVersion) {
        if (schemaVersion == null) {
            return null;
        }
        String normalized = schemaVersion.strip();
        return normalized.isBlank() || normalized.length() > 20
                ? null
                : normalized;
    }

    private String safeCode(String code) {
        if (code == null || !code.matches("^[A-Z0-9_]{1,100}$")) {
            return "EXTERNAL_SERVICE_ERROR";
        }
        return code;
    }

    private record Claim(
            UUID jobId,
            UUID sessionId,
            UUID answerId,
            UUID workerToken,
            InterviewJobType type,
            AnswerAnalysisRequest request
    ) {
    }
}
