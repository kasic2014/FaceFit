package com.facefit.backend.jobposting.application;

import com.fasterxml.jackson.databind.JsonNode;
import com.facefit.backend.common.api.PageResponse;
import com.facefit.backend.common.exception.InvalidJobPostingStateException;
import com.facefit.backend.common.exception.ResourceInUseException;
import com.facefit.backend.common.exception.ResourceNotFoundException;
import com.facefit.backend.common.exception.ResourceNotReadyException;
import com.facefit.backend.common.exception.UnsupportedInputTypeException;
import com.facefit.backend.jobposting.api.JobPostingDetailResponse;
import com.facefit.backend.jobposting.api.JobPostingPatchRequest;
import com.facefit.backend.jobposting.api.JobPostingSummaryResponse;
import com.facefit.backend.jobposting.domain.JobPosting;
import com.facefit.backend.jobposting.domain.JobPostingInputType;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;
import com.facefit.backend.jobposting.repository.JobPostingRepository;
import com.facefit.backend.jobposting.storage.JobPostingStorage;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.onboarding.application.OnboardingService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.time.OffsetDateTime;
import java.util.EnumSet;
import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class JobPostingService {

    public static final int MAX_RAW_TEXT_CHARACTERS = 50_000;
    private static final int MAX_PAGE_SIZE = 100;
    private static final Set<InterviewSessionStatus> NON_TERMINAL_SESSION_STATUSES =
            EnumSet.of(
                    InterviewSessionStatus.DRAFT,
                    InterviewSessionStatus.IN_PROGRESS,
                    InterviewSessionStatus.INTERVIEW_COMPLETED,
                    InterviewSessionStatus.ANALYZING
            );
    private static final int SHORT_FIELD_LIMIT = 500;
    private static final int LONG_FIELD_LIMIT = 10_000;
    private static final Set<String> REQUIRED_FIELDS = Set.of(
            "companyName",
            "targetRole",
            "mainResponsibilities",
            "qualifications"
    );
    private static final Sort POSTING_SORT = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("jobPostingId")
    );

    private final OnboardingService onboardingService;
    private final JobPostingFileValidator fileValidator;
    private final JobPostingObjectKeyFactory objectKeyFactory;
    private final JobPostingStorage storage;
    private final JobPostingRepository repository;
    private final InterviewSessionRepository interviewSessionRepository;
    private final TransactionTemplate transactionTemplate;
    private final ApplicationEventPublisher eventPublisher;

    @Value("${facefit.storage.supabase.job-postings-bucket:job-postings}")
    private String storageBucket;

    public JobPosting createFile(
            Jwt jwt,
            String inputType,
            MultipartFile file,
            String rawText
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        if (!JobPostingInputType.FILE.name().equals(inputType)
                || rawText != null) {
            throw new UnsupportedInputTypeException();
        }
        ValidatedJobPostingFile validated = fileValidator.validate(file);
        UUID jobPostingId = UUID.randomUUID();
        String objectKey = objectKeyFactory.create(
                profile.getUserId(),
                jobPostingId,
                validated.extension()
        );

        storage.upload(
                storageBucket,
                objectKey,
                validated.mimeType(),
                validated.content()
        );
        try {
            JobPosting saved = transactionTemplate.execute(status -> {
                JobPosting posting = repository.saveAndFlush(JobPosting.createFile(
                        jobPostingId,
                        profile,
                        validated.originalFileName(),
                        storageBucket,
                        objectKey,
                        validated.mimeType(),
                        validated.size()
                ));
                eventPublisher.publishEvent(new JobPostingRegisteredEvent(jobPostingId));
                return posting;
            });
            if (saved == null) {
                throw new IllegalStateException("지원공고를 저장할 수 없습니다.");
            }
            return saved;
        } catch (RuntimeException databaseFailure) {
            compensateUploadedObject(objectKey);
            throw databaseFailure;
        }
    }

    public JobPosting createText(Jwt jwt, String inputType, String rawText) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        if (!JobPostingInputType.TEXT.name().equals(inputType)) {
            throw new UnsupportedInputTypeException();
        }
        validateRawText(rawText);
        UUID jobPostingId = UUID.randomUUID();
        JobPosting saved = transactionTemplate.execute(status -> {
            JobPosting posting = repository.saveAndFlush(
                    JobPosting.createText(jobPostingId, profile, rawText)
            );
            eventPublisher.publishEvent(new JobPostingRegisteredEvent(jobPostingId));
            return posting;
        });
        if (saved == null) {
            throw new IllegalStateException("지원공고를 저장할 수 없습니다.");
        }
        return saved;
    }

    @Transactional(readOnly = true)
    public PageResponse<JobPostingSummaryResponse> findAll(
            Jwt jwt,
            JobPostingProcessingStatus processingStatus,
            int page,
            int size
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        validatePage(page, size);
        Page<JobPosting> result = repository.findActiveByOwner(
                profile.getUserId(),
                processingStatus,
                PageRequest.of(page, size, POSTING_SORT)
        );
        return PageResponse.from(result, JobPostingSummaryResponse::from);
    }

    @Transactional(readOnly = true)
    public JobPostingDetailResponse findOne(Jwt jwt, UUID jobPostingId) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        JobPosting posting = repository
                .findByJobPostingIdAndProfile_UserIdAndDeletedAtIsNull(
                        jobPostingId,
                        profile.getUserId()
                )
                .orElseThrow(ResourceNotFoundException::new);
        return JobPostingDetailResponse.from(posting);
    }

    public JobPostingDetailResponse patch(
            Jwt jwt,
            UUID jobPostingId,
            JobPostingPatchRequest request
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        validatePatchShape(request);
        JobPosting result = transactionTemplate.execute(status -> {
            JobPosting posting = repository.findActiveOwnedByIdForUpdate(
                    jobPostingId,
                    profile.getUserId()
            ).orElseThrow(ResourceNotFoundException::new);
            if (posting.getProcessingStatus() == JobPostingProcessingStatus.PROCESSING) {
                throw new ResourceNotReadyException();
            }
            if (posting.getProcessingStatus() != JobPostingProcessingStatus.READY
                    && posting.getProcessingStatus() != JobPostingProcessingStatus.FAILED) {
                throw new InvalidJobPostingStateException("수정할 수 없는 지원공고 상태입니다.");
            }
            posting.applyUserPatch(
                    patched(request, "companyName", posting.getCompanyName(), SHORT_FIELD_LIMIT),
                    patched(request, "targetRole", posting.getTargetRole(), SHORT_FIELD_LIMIT),
                    patched(
                            request,
                            "mainResponsibilities",
                            posting.getMainResponsibilities(),
                            LONG_FIELD_LIMIT
                    ),
                    patched(request, "qualifications", posting.getQualifications(), LONG_FIELD_LIMIT),
                    patched(
                            request,
                            "preferredQualifications",
                            posting.getPreferredQualifications(),
                            LONG_FIELD_LIMIT
                    ),
                    patched(
                            request,
                            "technologiesTools",
                            posting.getTechnologiesTools(),
                            LONG_FIELD_LIMIT
                    ),
                    patched(
                            request,
                            "coreCompetencies",
                            posting.getCoreCompetencies(),
                            LONG_FIELD_LIMIT
                    ),
                    patched(
                            request,
                            "companyBusinessIntro",
                            posting.getCompanyBusinessIntro(),
                            LONG_FIELD_LIMIT
                    )
            );
            return repository.saveAndFlush(posting);
        });
        if (result == null) {
            throw new ResourceNotFoundException();
        }
        return JobPostingDetailResponse.from(result);
    }

    public void delete(Jwt jwt, UUID jobPostingId) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        DeletedObject deleted = transactionTemplate.execute(status -> {
            JobPosting posting = repository.findActiveOwnedByIdForUpdate(
                    jobPostingId,
                    profile.getUserId()
            ).orElseThrow(ResourceNotFoundException::new);
            if (interviewSessionRepository.existsNonTerminalReferenceToJobPosting(
                    profile.getUserId(),
                    jobPostingId,
                    NON_TERMINAL_SESSION_STATUSES
            )) {
                throw new ResourceInUseException();
            }
            posting.softDelete(OffsetDateTime.now());
            repository.saveAndFlush(posting);
            return new DeletedObject(
                    posting.getInputType(),
                    posting.getStorageBucket(),
                    posting.getStoragePath()
            );
        });
        if (deleted == null) {
            throw new ResourceNotFoundException();
        }
        if (deleted.inputType() == JobPostingInputType.TEXT) {
            return;
        }
        try {
            storage.delete(deleted.bucket(), deleted.objectKey());
        } catch (RuntimeException storageFailure) {
            restoreSoftDelete(jobPostingId, profile.getUserId());
            throw storageFailure;
        }
    }

    private void validateRawText(String rawText) {
        if (rawText == null || rawText.isBlank()) {
            throw new IllegalArgumentException("rawText는 공백이 아닌 문자열이어야 합니다.");
        }
        if (rawText.codePointCount(0, rawText.length()) > MAX_RAW_TEXT_CHARACTERS) {
            throw new IllegalArgumentException("rawText는 50,000자 이하여야 합니다.");
        }
    }

    private void validatePatchShape(JobPostingPatchRequest request) {
        if (request == null || request.isEmpty()) {
            throw new IllegalArgumentException("수정할 필드를 하나 이상 전달해야 합니다.");
        }
        if (!JobPostingPatchRequest.ALLOWED_FIELDS.containsAll(request.fieldNames())) {
            throw new IllegalArgumentException("수정할 수 없는 필드가 포함되어 있습니다.");
        }
    }

    private String patched(
            JobPostingPatchRequest request,
            String field,
            String current,
            int maxCharacters
    ) {
        if (!request.contains(field)) {
            return current;
        }
        JsonNode node = request.value(field);
        if (node == null || node.isNull()) {
            if (REQUIRED_FIELDS.contains(field)) {
                throw new IllegalArgumentException(field + " 필수 필드는 null로 변경할 수 없습니다.");
            }
            return null;
        }
        if (!node.isTextual()) {
            throw new IllegalArgumentException(field + " 필드는 문자열 또는 null이어야 합니다.");
        }
        String value = node.textValue().strip();
        if (value.isBlank()) {
            throw new IllegalArgumentException(field + " 필드는 빈 문자열일 수 없습니다.");
        }
        if (value.codePointCount(0, value.length()) > maxCharacters) {
            throw new IllegalArgumentException(
                    field + " 필드는 " + maxCharacters + "자 이하여야 합니다."
            );
        }
        return value;
    }

    private void validatePage(int page, int size) {
        if (page < 0 || size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("page는 0 이상, size는 1 이상 100 이하여야 합니다.");
        }
    }

    private void compensateUploadedObject(String objectKey) {
        try {
            storage.delete(storageBucket, objectKey);
        } catch (RuntimeException compensationFailure) {
            log.error("Job posting upload compensation failed");
        }
    }

    private void restoreSoftDelete(UUID jobPostingId, UUID userId) {
        try {
            transactionTemplate.executeWithoutResult(status ->
                    repository.findByIdForUpdate(jobPostingId)
                            .filter(posting -> posting.getProfile().getUserId().equals(userId))
                            .ifPresent(posting -> {
                                posting.restore();
                                repository.saveAndFlush(posting);
                            })
            );
        } catch (RuntimeException compensationFailure) {
            log.error("Job posting delete compensation failed");
        }
    }

    private record DeletedObject(
            JobPostingInputType inputType,
            String bucket,
            String objectKey
    ) {
    }
}
