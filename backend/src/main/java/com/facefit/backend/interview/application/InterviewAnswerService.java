package com.facefit.backend.interview.application;

import com.facefit.backend.common.exception.InterviewProgressException;
import com.facefit.backend.common.exception.InvalidInterviewSessionStateException;
import com.facefit.backend.common.exception.ResourceNotFoundException;
import com.facefit.backend.interview.api.InterviewAnswerCreatedResponse;
import com.facefit.backend.interview.api.InterviewAnswerResponse;
import com.facefit.backend.interview.domain.AnswerEndedBy;
import com.facefit.backend.interview.domain.ApiIdempotencyRecord;
import com.facefit.backend.interview.domain.InterviewAnswer;
import com.facefit.backend.interview.domain.InterviewAnswerStatus;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.InterviewProcessingJob;
import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.domain.InterviewTurn;
import com.facefit.backend.interview.repository.InterviewAnswerRepository;
import com.facefit.backend.interview.repository.InterviewProcessingJobRepository;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import com.facefit.backend.interview.repository.InterviewTurnRepository;
import com.facefit.backend.interview.storage.InterviewAnswerStorage;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.onboarding.application.OnboardingService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class InterviewAnswerService {

    private static final String POST = "POST";
    private static final List<InterviewJobType> ANSWER_JOB_TYPES_WITH_VOICE = List.of(
            InterviewJobType.STT,
            InterviewJobType.CV,
            InterviewJobType.VOICE,
            InterviewJobType.CONTENT
    );
    private static final List<InterviewJobType> ANSWER_JOB_TYPES_WITHOUT_VOICE = List.of(
            InterviewJobType.STT,
            InterviewJobType.CV,
            InterviewJobType.CONTENT
    );

    private final OnboardingService onboardingService;
    private final AnswerMediaValidator mediaValidator;
    private final InterviewAnswerObjectKeyFactory objectKeyFactory;
    private final InterviewAnswerStorage storage;
    private final InterviewSessionRepository sessionRepository;
    private final InterviewTurnRepository turnRepository;
    private final InterviewAnswerRepository answerRepository;
    private final InterviewProcessingJobRepository jobRepository;
    private final IdempotencyService idempotencyService;
    private final TransactionTemplate transactionTemplate;
    private final ApplicationEventPublisher eventPublisher;

    @Value("${facefit.storage.supabase.interview-answers-bucket:interview-answers}")
    private String storageBucket;

    public IdempotentResult<InterviewAnswerCreatedResponse> submit(
            Jwt jwt,
            UUID sessionId,
            String idempotencyKey,
            UUID questionId,
            MultipartFile file,
            Integer recordedDurationSeconds,
            AnswerEndedBy endedBy
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        String key = idempotencyService.requireValidKey(idempotencyKey);
        if (questionId == null || endedBy == null) {
            throw new IllegalArgumentException(
                    "questionId, file, recordedDurationSec, endedBy는 필수입니다."
            );
        }
        ValidatedAnswerMedia media = mediaValidator.validate(
                file,
                recordedDurationSeconds
        );
        String uri = "/api/v1/interview-sessions/" + sessionId + "/answers";
        String requestHash = idempotencyService.requestHash(
                "ANSWER-001|"
                        + sessionId + "|"
                        + questionId + "|"
                        + media.size() + "|"
                        + media.sha256() + "|"
                        + media.mimeType() + "|"
                        + recordedDurationSeconds + "|"
                        + endedBy
        );

        Reservation reservation = transactionTemplate.execute(status -> reserve(
                profile,
                sessionId,
                questionId,
                key,
                uri,
                requestHash,
                media,
                recordedDurationSeconds,
                endedBy
        ));
        if (reservation == null) {
            throw new IllegalStateException("답변 업로드를 예약할 수 없습니다.");
        }
        if (reservation.replay()) {
            return new IdempotentResult<>(
                    reservation.httpStatus(),
                    reservation.replayResponse()
            );
        }

        try {
            storage.upload(
                    storageBucket,
                    reservation.objectKey(),
                    media.mimeType(),
                    media.content()
            );
        } catch (RuntimeException uploadFailure) {
            compensateUploadFailure(reservation);
            throw uploadFailure;
        }

        try {
            IdempotentResult<InterviewAnswerCreatedResponse> result =
                    transactionTemplate.execute(status -> finalizeAnswer(
                            profile.getUserId(),
                            reservation
                    ));
            if (result == null) {
                throw new IllegalStateException("답변을 확정할 수 없습니다.");
            }
            return result;
        } catch (RuntimeException databaseFailure) {
            compensateAfterFinalizeFailure(reservation);
            throw databaseFailure;
        }
    }

    @org.springframework.transaction.annotation.Transactional(readOnly = true)
    public InterviewAnswerResponse findOne(Jwt jwt, UUID answerId) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        InterviewAnswer answer = answerRepository
                .findByAnswerIdAndProfile_UserId(answerId, profile.getUserId())
                .orElseThrow(ResourceNotFoundException::new);
        List<InterviewProcessingJob> jobs =
                jobRepository.findAllByAnswer_AnswerIdOrderByType(answerId);
        InterviewTurn next = answer.isConfirmed()
                && answer.getSession().getStatus() == InterviewSessionStatus.IN_PROGRESS
                ? turnRepository.findFirstUnanswered(
                        answer.getSession().getSessionId()
                ).orElse(null)
                : null;
        return new InterviewAnswerResponse(
                answer.getAnswerId(),
                answer.getSession().getSessionId(),
                answer.getTurn().getTurnId(),
                answer.getStatus(),
                answer.isNextQuestionReady(),
                next == null ? null : next.getTurnId(),
                jobs.stream()
                        .map(job -> new InterviewAnswerResponse.ProcessingStep(
                                job.getType(),
                                job.getStatus(),
                                job.getAttemptCount(),
                                job.getMaxAttempts(),
                                job.getFailureCode()
                        ))
                        .toList(),
                answer.getCreatedAt(),
                answer.getConfirmedAt()
        );
    }

    private Reservation reserve(
            Profile profile,
            UUID sessionId,
            UUID questionId,
            String key,
            String uri,
            String requestHash,
            ValidatedAnswerMedia media,
            int recordedDurationSeconds,
            AnswerEndedBy endedBy
    ) {
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
            return Reservation.replay(
                    idempotency.responseStatus(),
                    idempotencyService.readResponse(
                            idempotency.responseBody(),
                            InterviewAnswerCreatedResponse.class
                    )
            );
        }
        if (session.getStatus() != InterviewSessionStatus.IN_PROGRESS) {
            throw new InvalidInterviewSessionStateException();
        }

        InterviewTurn turn = turnRepository.findByIdAndSessionForUpdate(
                questionId,
                sessionId
        ).orElseThrow(ResourceNotFoundException::new);
        InterviewAnswer existing = answerRepository
                .findByTurn_TurnId(questionId)
                .orElse(null);
        if (existing != null) {
            if (existing.isConfirmed()) {
                throw new InterviewProgressException(
                        HttpStatus.CONFLICT,
                        "ANSWER_ALREADY_SUBMITTED",
                        "이미 답변이 제출된 질문입니다."
                );
            }
            throw new InterviewProgressException(
                    HttpStatus.CONFLICT,
                    "IDEMPOTENCY_REQUEST_IN_PROGRESS",
                    "이 질문의 답변 업로드가 처리 중입니다."
            );
        }
        InterviewTurn current = turnRepository
                .findFirstUnanswered(sessionId)
                .orElseThrow(InvalidInterviewSessionStateException::new);
        if (!current.getTurnId().equals(turn.getTurnId())) {
            throw new InvalidInterviewSessionStateException(
                    "현재 질문에만 답변할 수 있습니다."
            );
        }

        UUID answerId = UUID.randomUUID();
        String objectKey = objectKeyFactory.create(
                sessionId,
                turn.getTurnId(),
                answerId,
                media.extension()
        );
        answerRepository.saveAndFlush(InterviewAnswer.reserve(
                answerId,
                session,
                turn,
                profile,
                storageBucket,
                objectKey,
                media.mimeType(),
                media.size(),
                media.sha256(),
                recordedDurationSeconds,
                media.durationMillis(),
                endedBy
        ));
        return Reservation.created(
                answerId,
                sessionId,
                turn.getTurnId(),
                idempotency.record().getId(),
                objectKey
        );
    }

    private IdempotentResult<InterviewAnswerCreatedResponse> finalizeAnswer(
            UUID userId,
            Reservation reservation
    ) {
        InterviewSession session = sessionRepository.findOwnedByIdForUpdate(
                reservation.sessionId(),
                userId
        ).orElseThrow(ResourceNotFoundException::new);
        InterviewTurn turn = turnRepository.findByIdAndSessionForUpdate(
                reservation.turnId(),
                reservation.sessionId()
        ).orElseThrow(ResourceNotFoundException::new);
        InterviewAnswer answer = answerRepository.findByIdForUpdate(
                reservation.answerId()
        ).orElseThrow(ResourceNotFoundException::new);
        if (session.getStatus() != InterviewSessionStatus.IN_PROGRESS
                || answer.getStatus() != InterviewAnswerStatus.UPLOADING) {
            throw new InvalidInterviewSessionStateException();
        }

        List<InterviewJobType> answerJobTypes = session.isVoiceAnalysisEnabled()
                ? ANSWER_JOB_TYPES_WITH_VOICE
                : ANSWER_JOB_TYPES_WITHOUT_VOICE;
        List<UUID> jobIds = new ArrayList<>(answerJobTypes.size());
        for (InterviewJobType type : answerJobTypes) {
            UUID jobId = UUID.randomUUID();
            jobRepository.save(InterviewProcessingJob.answerAnalysis(
                    jobId,
                    session,
                    answer,
                    type
            ));
            jobIds.add(jobId);
        }
        jobRepository.flush();
        answer.confirm();
        session.moveCurrentQuestionOrder(
                turn.getQuestionOrder() < InterviewProgressService.QUESTION_COUNT
                        ? turn.getQuestionOrder() + 1
                        : null
        );
        answerRepository.saveAndFlush(answer);
        sessionRepository.saveAndFlush(session);

        String nextStatus =
                turn.getQuestionOrder() < InterviewProgressService.QUESTION_COUNT
                        ? "READY"
                        : "ALL_QUESTIONS_ANSWERED";
        InterviewAnswerCreatedResponse response =
                new InterviewAnswerCreatedResponse(
                        answer.getAnswerId(),
                        turn.getTurnId(),
                        answer.getStatus(),
                        nextStatus
                );
        ApiIdempotencyRecord record = idempotencyService.findForUpdate(
                reservation.idempotencyRecordId()
        );
        idempotencyService.complete(record, HttpStatus.OK.value(), response);
        eventPublisher.publishEvent(new AnswerAnalysisRequestedEvent(jobIds));
        return new IdempotentResult<>(HttpStatus.OK.value(), response);
    }

    private void cleanupReservation(Reservation reservation) {
        transactionTemplate.executeWithoutResult(status -> {
            answerRepository.deleteById(reservation.answerId());
            answerRepository.flush();
            idempotencyService.delete(reservation.idempotencyRecordId());
        });
    }

    private void compensateAfterFinalizeFailure(Reservation reservation) {
        try {
            storage.delete(storageBucket, reservation.objectKey());
            cleanupReservation(reservation);
        } catch (RuntimeException compensationFailure) {
            log.error(
                    "Answer upload compensation failed answerId={}",
                    reservation.answerId()
            );
        }
    }

    private void compensateUploadFailure(Reservation reservation) {
        try {
            storage.delete(storageBucket, reservation.objectKey());
            cleanupReservation(reservation);
        } catch (RuntimeException compensationFailure) {
            log.error(
                    "Answer failed-upload reconciliation required answerId={}",
                    reservation.answerId()
            );
        }
    }

    private record Reservation(
            boolean replay,
            int httpStatus,
            InterviewAnswerCreatedResponse replayResponse,
            UUID answerId,
            UUID sessionId,
            UUID turnId,
            UUID idempotencyRecordId,
            String objectKey
    ) {
        static Reservation replay(
                int status,
                InterviewAnswerCreatedResponse response
        ) {
            return new Reservation(
                    true,
                    status,
                    response,
                    null,
                    null,
                    null,
                    null,
                    null
            );
        }

        static Reservation created(
                UUID answerId,
                UUID sessionId,
                UUID turnId,
                UUID idempotencyRecordId,
                String objectKey
        ) {
            return new Reservation(
                    false,
                    0,
                    null,
                    answerId,
                    sessionId,
                    turnId,
                    idempotencyRecordId,
                    objectKey
            );
        }
    }
}
