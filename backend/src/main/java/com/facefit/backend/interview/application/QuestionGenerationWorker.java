package com.facefit.backend.interview.application;

import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.InterviewProcessingJob;
import com.facefit.backend.interview.domain.InterviewQuestionType;
import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.domain.InterviewTurn;
import com.facefit.backend.interview.domain.JobPostingSnapshot;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.integration.QuestionGenerationPort;
import com.facefit.backend.interview.integration.QuestionGenerationRequest;
import com.facefit.backend.interview.integration.QuestionGenerationResponse;
import com.facefit.backend.interview.repository.InterviewProcessingJobRepository;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import com.facefit.backend.interview.repository.InterviewTurnRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

import java.text.Normalizer;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Component
@RequiredArgsConstructor
public class QuestionGenerationWorker {

    private static final String SCHEMA_VERSION = "1.0";
    private static final Map<InterviewQuestionType, Integer> REQUIRED_TYPE_COUNTS =
            Map.of(
                    InterviewQuestionType.INTRODUCTION, 1,
                    InterviewQuestionType.EXPERIENCE, 3,
                    InterviewQuestionType.JOB_ROLE, 3,
                    InterviewQuestionType.BEHAVIORAL, 2,
                    InterviewQuestionType.CLOSING, 1
            );

    private final InterviewProcessingJobRepository jobRepository;
    private final InterviewSessionRepository sessionRepository;
    private final InterviewTurnRepository turnRepository;
    private final ObjectProvider<QuestionGenerationPort> portProvider;
    private final ExternalCallExecutor externalCallExecutor;
    private final TransactionTemplate transactionTemplate;

    @Value("${facefit.interview.processing.question-timeout-seconds:60}")
    private long timeoutSeconds;

    public void process(UUID jobId) {
        Claim claim = claim(jobId);
        if (claim == null) {
            return;
        }
        QuestionGenerationPort port = portProvider.getIfAvailable();
        if (port == null) {
            fail(claim, "QUESTION_AI_ADAPTER_NOT_CONFIGURED", false);
            return;
        }

        PortResult<QuestionGenerationResponse> result = externalCallExecutor.call(
                () -> port.generate(claim.request()),
                Duration.ofSeconds(timeoutSeconds)
        );
        if (result instanceof PortResult.Success<?> success
                && success.value() instanceof QuestionGenerationResponse response) {
            try {
                List<ValidatedQuestion> questions = validate(
                        claim.jobId(),
                        response
                );
                complete(claim, questions);
            } catch (QuestionResponseValidationException invalid) {
                fail(claim, "QUESTION_AI_RESPONSE_INVALID", true);
            }
        } else if (result instanceof PortResult.RetryableFailure<?> failure) {
            fail(claim, safeCode(failure.errorCode()), true);
        } else if (result instanceof PortResult.PermanentFailure<?> failure) {
            fail(claim, safeCode(failure.errorCode()), false);
        } else {
            fail(claim, "QUESTION_AI_RESPONSE_INVALID", true);
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
                    || job.getType() != InterviewJobType.QUESTION_GENERATION
                    || session.getStatus() != InterviewSessionStatus.DRAFT) {
                return null;
            }
            UUID workerToken = UUID.randomUUID();
            OffsetDateTime now = OffsetDateTime.now();
            Duration staleAfter = Duration.ofSeconds(timeoutSeconds);
            if (job.failExhaustedStaleClaim(now, staleAfter)) {
                jobRepository.saveAndFlush(job);
                return null;
            }
            if (!job.claim(
                    workerToken,
                    now,
                    staleAfter
            )) {
                return null;
            }
            jobRepository.saveAndFlush(job);
            return new Claim(
                    jobId,
                    sessionId,
                    workerToken,
                    request(job, session)
            );
        });
    }

    private QuestionGenerationRequest request(
            InterviewProcessingJob job,
            InterviewSession session
    ) {
        return new QuestionGenerationRequest(
                SCHEMA_VERSION,
                job.getJobId(),
                "ko-KR",
                session.getPersona(),
                session.getDifficulty(),
                new QuestionGenerationRequest.QuestionPolicy(
                        InterviewProgressService.QUESTION_COUNT,
                        false
                ),
                new QuestionGenerationRequest.DocumentText(
                        session.getResumeDocument().getExtractedText()
                ),
                session.getCoverLetterDocument() == null
                        ? null
                        : new QuestionGenerationRequest.DocumentText(
                                session.getCoverLetterDocument().getExtractedText()
                        ),
                new JobPostingSnapshot(
                        session.getCompanyName(),
                        session.getTargetRole(),
                        session.getMainResponsibilities(),
                        session.getQualifications(),
                        session.getPreferredQualifications(),
                        session.getTechnologiesTools(),
                        session.getCoreCompetencies(),
                        session.getCompanyBusinessIntro()
                )
        );
    }

    private List<ValidatedQuestion> validate(
            UUID jobId,
            QuestionGenerationResponse response
    ) {
        if (response == null
                || !SCHEMA_VERSION.equals(response.schemaVersion())
                || !jobId.equals(response.generationRequestId())
                || response.questions() == null
                || response.questions().size() != InterviewProgressService.QUESTION_COUNT) {
            throw new QuestionResponseValidationException();
        }

        List<QuestionGenerationResponse.GeneratedQuestion> ordered =
                new ArrayList<>(response.questions());
        ordered.sort(Comparator.comparingInt(
                QuestionGenerationResponse.GeneratedQuestion::order
        ));
        Set<String> texts = new HashSet<>();
        EnumMap<InterviewQuestionType, Integer> typeCounts =
                new EnumMap<>(InterviewQuestionType.class);
        List<ValidatedQuestion> validated = new ArrayList<>(ordered.size());
        for (int index = 0; index < ordered.size(); index++) {
            QuestionGenerationResponse.GeneratedQuestion question = ordered.get(index);
            if (question == null
                    || question.order() != index + 1
                    || question.type() == null) {
                throw new QuestionResponseValidationException();
            }
            String category = normalize(question.category(), 100);
            String text = normalize(question.text(), 500);
            if (!texts.add(text)) {
                throw new QuestionResponseValidationException();
            }
            typeCounts.merge(question.type(), 1, Integer::sum);
            validated.add(new ValidatedQuestion(
                    question.order(),
                    question.type(),
                    category,
                    text
            ));
        }
        if (!REQUIRED_TYPE_COUNTS.equals(typeCounts)) {
            throw new QuestionResponseValidationException();
        }
        return List.copyOf(validated);
    }

    private String normalize(String value, int maxCodePoints) {
        if (value == null) {
            throw new QuestionResponseValidationException();
        }
        String normalized = Normalizer.normalize(value.strip(), Normalizer.Form.NFC);
        if (normalized.isBlank()
                || normalized.codePointCount(0, normalized.length()) > maxCodePoints
                || normalized.codePoints().anyMatch(Character::isISOControl)) {
            throw new QuestionResponseValidationException();
        }
        return normalized;
    }

    private void complete(Claim claim, List<ValidatedQuestion> questions) {
        transactionTemplate.executeWithoutResult(status -> {
            InterviewSession session = sessionRepository
                    .findByIdForUpdate(claim.sessionId())
                    .orElse(null);
            InterviewProcessingJob job = jobRepository
                    .findByIdForUpdate(claim.jobId())
                    .orElse(null);
            if (session == null
                    || job == null
                    || !job.isOwnedBy(claim.workerToken())) {
                return;
            }
            if (session.getStatus() != InterviewSessionStatus.DRAFT
                    || turnRepository.countBySession_SessionId(claim.sessionId()) != 0) {
                job.fail(
                        claim.workerToken(),
                        "QUESTION_STATE_CONFLICT",
                        false,
                        OffsetDateTime.now()
                );
                jobRepository.saveAndFlush(job);
                return;
            }
            List<InterviewTurn> turns = questions.stream()
                    .map(question -> InterviewTurn.create(
                            UUID.randomUUID(),
                            session,
                            claim.jobId(),
                            question.order(),
                            question.type(),
                            question.category(),
                            question.text()
                    ))
                    .toList();
            turnRepository.saveAll(turns);
            turnRepository.flush();
            OffsetDateTime now = OffsetDateTime.now();
            job.succeed(claim.workerToken(), null, now);
            session.startAfterQuestionsGenerated(now);
            jobRepository.saveAndFlush(job);
            sessionRepository.saveAndFlush(session);
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
            if (session == null
                    || job == null
                    || !job.isOwnedBy(claim.workerToken())) {
                return;
            }
            if (retryable) {
                job.retry(claim.workerToken(), code, OffsetDateTime.now());
            } else {
                job.fail(
                        claim.workerToken(),
                        code,
                        false,
                        OffsetDateTime.now()
                );
            }
            jobRepository.saveAndFlush(job);
        });
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
            UUID workerToken,
            QuestionGenerationRequest request
    ) {
    }

    private record ValidatedQuestion(
            int order,
            InterviewQuestionType type,
            String category,
            String text
    ) {
    }

    private static final class QuestionResponseValidationException
            extends RuntimeException {
    }
}
