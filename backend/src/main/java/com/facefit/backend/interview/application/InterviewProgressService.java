package com.facefit.backend.interview.application;

import com.facefit.backend.common.exception.InterviewProgressException;
import com.facefit.backend.common.exception.InvalidInterviewSessionStateException;
import com.facefit.backend.common.exception.ResourceNotFoundException;
import com.facefit.backend.common.exception.ResourceNotReadyException;
import com.facefit.backend.document.domain.DocumentProcessingStatus;
import com.facefit.backend.interview.api.CurrentQuestion;
import com.facefit.backend.interview.api.CurrentQuestionResponse;
import com.facefit.backend.interview.api.InterviewCompletionRequest;
import com.facefit.backend.interview.api.InterviewCompletionResponse;
import com.facefit.backend.interview.api.InterviewStartResponse;
import com.facefit.backend.interview.domain.ApiIdempotencyRecord;
import com.facefit.backend.interview.domain.InterviewAnswerStatus;
import com.facefit.backend.interview.domain.InterviewCompletionType;
import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.InterviewProcessingJob;
import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.domain.InterviewTurn;
import com.facefit.backend.interview.repository.InterviewAnswerRepository;
import com.facefit.backend.interview.repository.InterviewProcessingJobRepository;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import com.facefit.backend.interview.repository.InterviewTurnRepository;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.onboarding.application.OnboardingService;
import lombok.RequiredArgsConstructor;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.EnumSet;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class InterviewProgressService {

    public static final int QUESTION_COUNT = 10;
    private static final String POST = "POST";

    private final OnboardingService onboardingService;
    private final InterviewSessionRepository sessionRepository;
    private final InterviewTurnRepository turnRepository;
    private final InterviewAnswerRepository answerRepository;
    private final InterviewProcessingJobRepository jobRepository;
    private final IdempotencyService idempotencyService;
    private final ApplicationEventPublisher eventPublisher;

    @Transactional
    public IdempotentResult<InterviewStartResponse> start(
            Jwt jwt,
            UUID sessionId,
            String idempotencyKey
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        String key = idempotencyService.requireValidKey(idempotencyKey);
        String uri = "/api/v1/interview-sessions/" + sessionId + "/start";
        String requestHash = idempotencyService.requestHash(
                "SESSION-004|" + sessionId
        );

        InterviewSession session = sessionRepository.findOwnedByIdForUpdate(
                sessionId,
                profile.getUserId()
        ).orElseThrow(ResourceNotFoundException::new);
        IdempotencyService.BeginResult idempotency = idempotencyService.begin(
                profile,
                POST,
                uri,
                key,
                requestHash
        );
        if (idempotency.replay()) {
            return new IdempotentResult<>(
                    idempotency.responseStatus(),
                    idempotencyService.readResponse(
                            idempotency.responseBody(),
                            InterviewStartResponse.class
                    )
            );
        }

        if (session.getStatus() != InterviewSessionStatus.DRAFT) {
            throw new InvalidInterviewSessionStateException();
        }
        validateStartResources(session);
        if (turnRepository.countBySession_SessionId(sessionId) != 0) {
            throw new InvalidInterviewSessionStateException(
                    "이미 질문이 생성된 세션입니다."
            );
        }
        if (jobRepository.existsBySession_SessionIdAndTypeAndStatusIn(
                sessionId,
                InterviewJobType.QUESTION_GENERATION,
                EnumSet.of(InterviewJobStatus.QUEUED, InterviewJobStatus.PROCESSING)
        )) {
            throw new InterviewProgressException(
                    HttpStatus.CONFLICT,
                    "IDEMPOTENCY_REQUEST_IN_PROGRESS",
                    "질문 생성 요청이 이미 처리 중입니다."
            );
        }

        UUID jobId = UUID.randomUUID();
        jobRepository.saveAndFlush(
                InterviewProcessingJob.questionGeneration(jobId, session)
        );
        InterviewStartResponse response = new InterviewStartResponse(
                sessionId,
                InterviewSessionStatus.DRAFT,
                InterviewJobStatus.QUEUED,
                null
        );
        idempotencyService.complete(
                idempotency.record(),
                HttpStatus.ACCEPTED.value(),
                response
        );
        eventPublisher.publishEvent(new QuestionGenerationRequestedEvent(jobId));
        return new IdempotentResult<>(HttpStatus.ACCEPTED.value(), response);
    }

    @Transactional(readOnly = true)
    public IdempotentResult<CurrentQuestionResponse> currentQuestion(
            Jwt jwt,
            UUID sessionId
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        InterviewSession session = sessionRepository.findOwnedById(
                sessionId,
                profile.getUserId()
        ).orElseThrow(ResourceNotFoundException::new);
        InterviewProcessingJob generationJob = jobRepository
                .findFirstBySession_SessionIdAndTypeOrderByCreatedAtDesc(
                        sessionId,
                        InterviewJobType.QUESTION_GENERATION
                )
                .orElse(null);

        if (session.getStatus() == InterviewSessionStatus.DRAFT) {
            if (generationJob == null) {
                throw new InvalidInterviewSessionStateException();
            }
            if (generationJob.getStatus() == InterviewJobStatus.QUEUED
                    || generationJob.getStatus() == InterviewJobStatus.PROCESSING) {
                return new IdempotentResult<>(
                        HttpStatus.ACCEPTED.value(),
                        new CurrentQuestionResponse(
                                sessionId,
                                InterviewSessionStatus.DRAFT,
                                generationJob.getStatus(),
                                null,
                                "QUESTION_GENERATION_IN_PROGRESS",
                                false,
                                false
                        )
                );
            }
            if (generationJob.getStatus() == InterviewJobStatus.FAILED) {
                throw new InterviewProgressException(
                        HttpStatus.SERVICE_UNAVAILABLE,
                        "QUESTION_GENERATION_FAILED",
                        "면접 질문을 생성하지 못했습니다.",
                        Boolean.TRUE.equals(generationJob.getFailureRetryable())
                );
            }
            throw new InvalidInterviewSessionStateException();
        }
        if (session.getStatus() != InterviewSessionStatus.IN_PROGRESS
                || generationJob == null
                || generationJob.getStatus() != InterviewJobStatus.SUCCEEDED) {
            throw new InvalidInterviewSessionStateException();
        }

        InterviewTurn turn = turnRepository.findFirstUnanswered(sessionId).orElse(null);
        if (turn == null) {
            return new IdempotentResult<>(
                    HttpStatus.OK.value(),
                    new CurrentQuestionResponse(
                            sessionId,
                            session.getStatus(),
                            generationJob.getStatus(),
                            null,
                            "ALL_QUESTIONS_ANSWERED",
                            false,
                            true
                    )
            );
        }
        return new IdempotentResult<>(
                HttpStatus.OK.value(),
                new CurrentQuestionResponse(
                        sessionId,
                        session.getStatus(),
                        generationJob.getStatus(),
                        new CurrentQuestion(
                                turn.getTurnId(),
                                turn.getQuestionOrder(),
                                turn.getQuestionType(),
                                turn.getQuestionCategory(),
                                turn.getQuestionText()
                        ),
                        null,
                        true,
                        false
                )
        );
    }

    @Transactional
    public IdempotentResult<InterviewCompletionResponse> complete(
            Jwt jwt,
            UUID sessionId,
            String idempotencyKey,
            InterviewCompletionRequest request
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        String key = idempotencyService.requireValidKey(idempotencyKey);
        if (request == null || request.completionType() == null) {
            throw new IllegalArgumentException("completionType은 필수입니다.");
        }
        String uri = "/api/v1/interview-sessions/" + sessionId + "/completion";
        String requestHash = idempotencyService.requestHash(
                "SESSION-005|" + sessionId + "|" + request.completionType()
        );

        InterviewSession session = sessionRepository.findOwnedByIdForUpdate(
                sessionId,
                profile.getUserId()
        ).orElseThrow(ResourceNotFoundException::new);
        IdempotencyService.BeginResult idempotency = idempotencyService.begin(
                profile,
                POST,
                uri,
                key,
                requestHash
        );
        if (idempotency.replay()) {
            return new IdempotentResult<>(
                    idempotency.responseStatus(),
                    idempotencyService.readResponse(
                            idempotency.responseBody(),
                            InterviewCompletionResponse.class
                    )
            );
        }

        if (isSameCompletedMeaning(session, request.completionType())) {
            InterviewCompletionResponse response = completionResponse(session);
            idempotencyService.complete(
                    idempotency.record(),
                    HttpStatus.OK.value(),
                    response
            );
            return new IdempotentResult<>(HttpStatus.OK.value(), response);
        }
        if (session.getStatus() != InterviewSessionStatus.IN_PROGRESS) {
            throw new InvalidInterviewSessionStateException();
        }
        if (answerRepository.existsBySession_SessionIdAndStatus(
                sessionId,
                InterviewAnswerStatus.UPLOADING
        )) {
            throw new InterviewProgressException(
                    HttpStatus.CONFLICT,
                    "IDEMPOTENCY_REQUEST_IN_PROGRESS",
                    "답변 업로드가 처리 중입니다."
            );
        }

        OffsetDateTime now = OffsetDateTime.now();
        if (request.completionType() == InterviewCompletionType.NORMAL) {
            long questions = turnRepository.countBySession_SessionId(sessionId);
            long answers = answerRepository
                    .countBySession_SessionIdAndConfirmedAtIsNotNull(sessionId);
            if (questions != QUESTION_COUNT || answers != QUESTION_COUNT) {
                throw new InterviewProgressException(
                        HttpStatus.CONFLICT,
                        "INCOMPLETE_INTERVIEW",
                        "필수 질문에 모두 답변해야 면접을 종료할 수 있습니다."
                );
            }
            session.completeInterview(now);
        } else {
            session.interruptInterview(now);
        }
        sessionRepository.saveAndFlush(session);
        InterviewCompletionResponse response = completionResponse(session);
        idempotencyService.complete(
                idempotency.record(),
                HttpStatus.OK.value(),
                response
        );
        if (request.completionType() == InterviewCompletionType.NORMAL) {
            eventPublisher.publishEvent(
                    new AnalysisOrchestrationRequestedEvent(sessionId)
            );
        }
        return new IdempotentResult<>(HttpStatus.OK.value(), response);
    }

    private void validateStartResources(InterviewSession session) {
        if (session.getResumeDocument().getDeletedAt() != null
                || session.getResumeDocument().getProcessingStatus()
                != DocumentProcessingStatus.READY
                || !hasText(session.getResumeDocument().getExtractedText())) {
            throw new ResourceNotReadyException();
        }
        if (session.getCoverLetterDocument() != null
                && (session.getCoverLetterDocument().getDeletedAt() != null
                || session.getCoverLetterDocument().getProcessingStatus()
                != DocumentProcessingStatus.READY
                || !hasText(session.getCoverLetterDocument().getExtractedText()))) {
            throw new ResourceNotReadyException();
        }
        if (session.getJobPosting().getDeletedAt() != null
                || session.getJobPosting().getProcessingStatus()
                != JobPostingProcessingStatus.READY
                || !hasText(session.getCompanyName())
                || !hasText(session.getTargetRole())
                || !hasText(session.getMainResponsibilities())
                || !hasText(session.getQualifications())
                || !hasText(session.getPersona())
                || !hasText(session.getDifficulty())) {
            throw new ResourceNotReadyException();
        }
    }

    private boolean isSameCompletedMeaning(
            InterviewSession session,
            InterviewCompletionType requested
    ) {
        return (session.getStatus() == InterviewSessionStatus.INTERVIEW_COMPLETED
                && requested == InterviewCompletionType.NORMAL)
                || (session.getStatus() == InterviewSessionStatus.INTERRUPTED
                && requested == InterviewCompletionType.USER_INTERRUPTED);
    }

    private InterviewCompletionResponse completionResponse(InterviewSession session) {
        OffsetDateTime endedAt =
                session.getCompletionType() == InterviewCompletionType.NORMAL
                        ? session.getInterviewCompletedAt()
                        : session.getInterruptedAt();
        return new InterviewCompletionResponse(
                session.getSessionId(),
                session.getStatus(),
                session.getCompletionType(),
                endedAt
        );
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
