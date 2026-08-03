package com.facefit.backend.interview.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.facefit.backend.common.exception.InvalidInterviewSessionStateException;
import com.facefit.backend.common.exception.InvalidSessionResourceException;
import com.facefit.backend.common.exception.ResourceNotFoundException;
import com.facefit.backend.common.exception.ResourceNotReadyException;
import com.facefit.backend.document.domain.CareerDocument;
import com.facefit.backend.document.domain.CareerDocumentType;
import com.facefit.backend.document.domain.DocumentProcessingStatus;
import com.facefit.backend.document.repository.CareerDocumentRepository;
import com.facefit.backend.interview.api.InterviewSessionCreateRequest;
import com.facefit.backend.interview.api.InterviewSessionPatchRequest;
import com.facefit.backend.interview.api.InterviewSessionResponse;
import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.domain.InterviewJobStatus;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.JobPostingSnapshot;
import com.facefit.backend.interview.repository.InterviewProcessingJobRepository;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import com.facefit.backend.jobposting.domain.JobPosting;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;
import com.facefit.backend.jobposting.repository.JobPostingRepository;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.onboarding.application.OnboardingService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.text.Normalizer;
import java.util.Objects;
import java.util.EnumSet;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class InterviewSessionService {

    private static final int MAX_PERSONA_CHARACTERS = 50;
    private static final int MAX_DIFFICULTY_CHARACTERS = 30;

    private final OnboardingService onboardingService;
    private final CareerDocumentRepository careerDocumentRepository;
    private final JobPostingRepository jobPostingRepository;
    private final InterviewSessionRepository interviewSessionRepository;
    private final InterviewProcessingJobRepository interviewProcessingJobRepository;

    @Transactional
    public InterviewSession create(Jwt jwt, InterviewSessionCreateRequest request) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        if (request == null
                || request.resumeDocumentId() == null
                || request.jobPostingId() == null) {
            throw new IllegalArgumentException(
                    "resumeDocumentId와 jobPostingId는 필수입니다."
            );
        }
        if (request.resumeDocumentId().equals(request.coverLetterDocumentId())) {
            throw new IllegalArgumentException(
                    "이력서와 자기소개서에 같은 문서를 지정할 수 없습니다."
            );
        }
        String persona = normalizeSetting(
                "persona",
                request.persona(),
                MAX_PERSONA_CHARACTERS
        );
        String difficulty = normalizeSetting(
                "difficulty",
                request.difficulty(),
                MAX_DIFFICULTY_CHARACTERS
        );

        UUID userId = profile.getUserId();
        CareerDocument resume = lockDocument(
                userId,
                request.resumeDocumentId(),
                CareerDocumentType.RESUME
        );
        CareerDocument coverLetter = request.coverLetterDocumentId() == null
                ? null
                : lockDocument(
                        userId,
                        request.coverLetterDocumentId(),
                        CareerDocumentType.COVER_LETTER
                );
        JobPosting jobPosting = lockJobPosting(userId, request.jobPostingId());
        JobPostingSnapshot snapshot = snapshotOf(jobPosting);

        return interviewSessionRepository.saveAndFlush(InterviewSession.create(
                UUID.randomUUID(),
                profile,
                resume,
                coverLetter,
                jobPosting,
                persona,
                difficulty,
                snapshot
        ));
    }

    @Transactional(readOnly = true)
    public InterviewSessionResponse findOne(Jwt jwt, UUID sessionId) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        InterviewSession session = interviewSessionRepository.findOwnedById(
                sessionId,
                profile.getUserId()
        ).orElseThrow(ResourceNotFoundException::new);
        return InterviewSessionResponse.from(session);
    }

    @Transactional
    public InterviewSessionResponse patch(
            Jwt jwt,
            UUID sessionId,
            InterviewSessionPatchRequest request
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        validatePatchShape(request);
        UUID userId = profile.getUserId();

        if (!interviewSessionRepository.existsBySessionIdAndProfile_UserId(
                sessionId,
                userId
        )) {
            throw new ResourceNotFoundException();
        }

        PatchValues patch = parsePatch(request);
        CareerDocument requestedResume = patch.resumePresent()
                ? lockDocument(userId, patch.resumeDocumentId(), CareerDocumentType.RESUME)
                : null;
        CareerDocument requestedCover = patch.coverPresent() && patch.coverLetterDocumentId() != null
                ? lockDocument(
                        userId,
                        patch.coverLetterDocumentId(),
                        CareerDocumentType.COVER_LETTER
                )
                : null;
        JobPosting requestedJobPosting = patch.jobPresent()
                ? lockJobPosting(userId, patch.jobPostingId())
                : null;

        InterviewSession session = interviewSessionRepository.findOwnedByIdForUpdate(
                sessionId,
                userId
        ).orElseThrow(ResourceNotFoundException::new);
        if (session.getStatus() != InterviewSessionStatus.DRAFT) {
            throw new InvalidInterviewSessionStateException();
        }
        if (interviewProcessingJobRepository
                .existsBySession_SessionIdAndTypeAndStatusIn(
                        sessionId,
                        InterviewJobType.QUESTION_GENERATION,
                        EnumSet.of(
                                InterviewJobStatus.QUEUED,
                                InterviewJobStatus.PROCESSING
                        )
                )) {
            throw new InvalidInterviewSessionStateException(
                    "질문 생성이 시작된 세션의 설정은 수정할 수 없습니다."
            );
        }

        UUID effectiveResumeId = patch.resumePresent()
                ? requestedResume.getDocumentId()
                : session.getResumeDocument().getDocumentId();
        UUID effectiveCoverId = patch.coverPresent()
                ? patch.coverLetterDocumentId()
                : session.getCoverLetterDocument() == null
                        ? null
                        : session.getCoverLetterDocument().getDocumentId();
        if (effectiveResumeId.equals(effectiveCoverId)) {
            throw new IllegalArgumentException(
                    "이력서와 자기소개서에 같은 문서를 지정할 수 없습니다."
            );
        }

        if (patch.resumePresent()
                && !requestedResume.getDocumentId()
                .equals(session.getResumeDocument().getDocumentId())) {
            session.changeResumeDocument(requestedResume);
        }
        if (patch.coverPresent()
                && !Objects.equals(
                        effectiveCoverId,
                        session.getCoverLetterDocument() == null
                                ? null
                                : session.getCoverLetterDocument().getDocumentId()
                )) {
            session.changeCoverLetterDocument(requestedCover);
        }
        if (patch.jobPresent()
                && !requestedJobPosting.getJobPostingId()
                .equals(session.getJobPosting().getJobPostingId())) {
            session.changeJobPosting(
                    requestedJobPosting,
                    snapshotOf(requestedJobPosting)
            );
        }
        if (patch.personaPresent()
                && !patch.persona().equals(session.getPersona())) {
            session.changePersona(patch.persona());
        }
        if (patch.difficultyPresent()
                && !patch.difficulty().equals(session.getDifficulty())) {
            session.changeDifficulty(patch.difficulty());
        }

        InterviewSession saved = interviewSessionRepository.saveAndFlush(session);
        return InterviewSessionResponse.from(saved);
    }

    private CareerDocument lockDocument(
            UUID userId,
            UUID documentId,
            CareerDocumentType requiredType
    ) {
        CareerDocument document = careerDocumentRepository.findActiveOwnedByIdForUpdate(
                documentId,
                userId
        ).orElseThrow(ResourceNotFoundException::new);
        if (document.getDocumentType() != requiredType) {
            throw new InvalidSessionResourceException(
                    requiredType == CareerDocumentType.RESUME
                            ? "이력서 문서만 이력서로 지정할 수 있습니다."
                            : "자기소개서 문서만 자기소개서로 지정할 수 있습니다."
            );
        }
        if (document.getProcessingStatus() != DocumentProcessingStatus.READY) {
            throw new ResourceNotReadyException();
        }
        return document;
    }

    private JobPosting lockJobPosting(UUID userId, UUID jobPostingId) {
        JobPosting posting = jobPostingRepository.findActiveOwnedByIdForUpdate(
                jobPostingId,
                userId
        ).orElseThrow(ResourceNotFoundException::new);
        if (posting.getProcessingStatus() != JobPostingProcessingStatus.READY) {
            throw new ResourceNotReadyException();
        }
        return posting;
    }

    private JobPostingSnapshot snapshotOf(JobPosting posting) {
        JobPostingSnapshot snapshot = JobPostingSnapshot.from(posting);
        if (!hasText(snapshot.companyName())
                || !hasText(snapshot.targetRole())
                || !hasText(snapshot.mainResponsibilities())
                || !hasText(snapshot.qualifications())) {
            throw new ResourceNotReadyException();
        }
        return snapshot;
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private String normalizeSetting(String field, String value, int maxCharacters) {
        if (value == null) {
            throw new IllegalArgumentException(field + " 필드는 필수입니다.");
        }
        String normalized = Normalizer.normalize(value.strip(), Normalizer.Form.NFC);
        if (normalized.isBlank()) {
            throw new IllegalArgumentException(field + " 필드는 빈 문자열일 수 없습니다.");
        }
        if (normalized.codePoints().anyMatch(Character::isISOControl)) {
            throw new IllegalArgumentException(field + " 필드에는 제어문자를 포함할 수 없습니다.");
        }
        if (normalized.codePointCount(0, normalized.length()) > maxCharacters) {
            throw new IllegalArgumentException(
                    field + " 필드는 " + maxCharacters + "자 이하여야 합니다."
            );
        }
        return normalized;
    }

    private void validatePatchShape(InterviewSessionPatchRequest request) {
        if (request == null || request.isEmpty()) {
            throw new IllegalArgumentException("수정할 필드를 하나 이상 전달해야 합니다.");
        }
        if (!InterviewSessionPatchRequest.ALLOWED_FIELDS.containsAll(request.fieldNames())) {
            throw new IllegalArgumentException("수정할 수 없는 필드가 포함되어 있습니다.");
        }
    }

    private PatchValues parsePatch(InterviewSessionPatchRequest request) {
        return new PatchValues(
                request.contains("resumeDocumentId"),
                requiredUuid(request, "resumeDocumentId"),
                request.contains("coverLetterDocumentId"),
                optionalUuid(request, "coverLetterDocumentId"),
                request.contains("jobPostingId"),
                requiredUuid(request, "jobPostingId"),
                request.contains("persona"),
                request.contains("persona")
                        ? normalizeSetting(
                                "persona",
                                requiredText(request, "persona"),
                                MAX_PERSONA_CHARACTERS
                        )
                        : null,
                request.contains("difficulty"),
                request.contains("difficulty")
                        ? normalizeSetting(
                                "difficulty",
                                requiredText(request, "difficulty"),
                                MAX_DIFFICULTY_CHARACTERS
                        )
                        : null
        );
    }

    private UUID requiredUuid(InterviewSessionPatchRequest request, String field) {
        if (!request.contains(field)) {
            return null;
        }
        JsonNode node = request.value(field);
        if (node == null || node.isNull()) {
            throw new IllegalArgumentException(field + " 필드는 null일 수 없습니다.");
        }
        return parseUuidNode(field, node);
    }

    private UUID optionalUuid(InterviewSessionPatchRequest request, String field) {
        if (!request.contains(field)) {
            return null;
        }
        JsonNode node = request.value(field);
        if (node == null || node.isNull()) {
            return null;
        }
        return parseUuidNode(field, node);
    }

    private UUID parseUuidNode(String field, JsonNode node) {
        if (!node.isTextual() || node.textValue().isBlank()) {
            throw new IllegalArgumentException(field + " 필드는 UUID 문자열이어야 합니다.");
        }
        try {
            return UUID.fromString(node.textValue());
        } catch (IllegalArgumentException exception) {
            throw new IllegalArgumentException(field + " 필드는 UUID 문자열이어야 합니다.");
        }
    }

    private String requiredText(InterviewSessionPatchRequest request, String field) {
        JsonNode node = request.value(field);
        if (node == null || node.isNull() || !node.isTextual()) {
            throw new IllegalArgumentException(field + " 필드는 문자열이어야 합니다.");
        }
        return node.textValue();
    }

    private record PatchValues(
            boolean resumePresent,
            UUID resumeDocumentId,
            boolean coverPresent,
            UUID coverLetterDocumentId,
            boolean jobPresent,
            UUID jobPostingId,
            boolean personaPresent,
            String persona,
            boolean difficultyPresent,
            String difficulty
    ) {
    }
}
