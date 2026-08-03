package com.facefit.backend.document.application;

import com.facefit.backend.common.api.PageResponse;
import com.facefit.backend.common.exception.ResourceInUseException;
import com.facefit.backend.common.exception.ResourceNotFoundException;
import com.facefit.backend.document.api.CareerDocumentResponse;
import com.facefit.backend.document.domain.CareerDocument;
import com.facefit.backend.document.domain.CareerDocumentType;
import com.facefit.backend.document.domain.DocumentProcessingStatus;
import com.facefit.backend.document.repository.CareerDocumentRepository;
import com.facefit.backend.document.storage.CareerDocumentStorage;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.onboarding.application.OnboardingService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.time.OffsetDateTime;
import java.util.EnumSet;
import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class CareerDocumentService {

    private static final int MAX_PAGE_SIZE = 100;
    private static final Set<InterviewSessionStatus> NON_TERMINAL_SESSION_STATUSES =
            EnumSet.of(
                    InterviewSessionStatus.DRAFT,
                    InterviewSessionStatus.IN_PROGRESS,
                    InterviewSessionStatus.INTERVIEW_COMPLETED,
                    InterviewSessionStatus.ANALYZING
            );
    private static final Sort DOCUMENT_SORT = Sort.by(
            Sort.Order.desc("createdAt"),
            Sort.Order.desc("documentId")
    );

    private final OnboardingService onboardingService;
    private final CareerDocumentFileValidator fileValidator;
    private final CareerDocumentObjectKeyFactory objectKeyFactory;
    private final CareerDocumentStorage storage;
    private final CareerDocumentRepository repository;
    private final InterviewSessionRepository interviewSessionRepository;
    private final TransactionTemplate transactionTemplate;

    @Value("${facefit.storage.supabase.career-documents-bucket:career-documents}")
    private String storageBucket;

    public CareerDocument create(
            Jwt jwt,
            CareerDocumentType documentType,
            MultipartFile file
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        ValidatedDocumentFile validated = fileValidator.validate(file);
        UUID documentId = UUID.randomUUID();
        String objectKey = objectKeyFactory.create(
                profile.getUserId(),
                documentId,
                validated.extension()
        );

        storage.upload(
                storageBucket,
                objectKey,
                validated.mimeType(),
                validated.content()
        );
        try {
            CareerDocument saved = transactionTemplate.execute(status ->
                    repository.saveAndFlush(CareerDocument.create(
                            documentId,
                            profile,
                            documentType,
                            validated.originalFileName(),
                            storageBucket,
                            objectKey,
                            validated.mimeType(),
                            validated.size()
                    ))
            );
            if (saved == null) {
                throw new IllegalStateException("문서 메타데이터를 저장할 수 없습니다.");
            }
            return saved;
        } catch (RuntimeException databaseFailure) {
            compensateUploadedObject(objectKey);
            throw databaseFailure;
        }
    }

    public PageResponse<CareerDocumentResponse> findAll(
            Jwt jwt,
            CareerDocumentType documentType,
            DocumentProcessingStatus status,
            int page,
            int size
    ) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        validatePage(page, size);
        Page<CareerDocument> result = repository.findActiveByOwner(
                profile.getUserId(),
                documentType,
                status,
                PageRequest.of(page, size, DOCUMENT_SORT)
        );
        return PageResponse.from(result, CareerDocumentResponse::from);
    }

    public CareerDocument findOne(Jwt jwt, UUID documentId) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        return repository.findByDocumentIdAndProfile_UserIdAndDeletedAtIsNull(
                documentId,
                profile.getUserId()
        ).orElseThrow(ResourceNotFoundException::new);
    }

    public void delete(Jwt jwt, UUID documentId) {
        Profile profile = onboardingService.requireCompletedOnboarding(jwt);
        DeletedObject deleted = transactionTemplate.execute(status -> {
            CareerDocument document = repository.findActiveOwnedByIdForUpdate(
                    documentId,
                    profile.getUserId()
            ).orElseThrow(ResourceNotFoundException::new);
            if (interviewSessionRepository.existsNonTerminalReferenceToDocument(
                    profile.getUserId(),
                    documentId,
                    NON_TERMINAL_SESSION_STATUSES
            )) {
                throw new ResourceInUseException();
            }
            document.softDelete(OffsetDateTime.now());
            repository.saveAndFlush(document);
            return new DeletedObject(document.getStorageBucket(), document.getStoragePath());
        });
        if (deleted == null) {
            throw new ResourceNotFoundException();
        }

        try {
            storage.delete(deleted.bucket(), deleted.objectKey());
        } catch (RuntimeException storageFailure) {
            restoreSoftDelete(documentId, profile.getUserId());
            throw storageFailure;
        }
    }

    private void compensateUploadedObject(String objectKey) {
        try {
            storage.delete(storageBucket, objectKey);
        } catch (RuntimeException compensationFailure) {
            log.error("Career document upload compensation failed");
        }
    }

    private void restoreSoftDelete(UUID documentId, UUID userId) {
        try {
            transactionTemplate.executeWithoutResult(status ->
                    repository.findById(documentId)
                            .filter(document -> document.getProfile().getUserId().equals(userId))
                            .ifPresent(document -> {
                                document.restore();
                                repository.saveAndFlush(document);
                            })
            );
        } catch (RuntimeException compensationFailure) {
            log.error("Career document delete compensation failed");
        }
    }

    private void validatePage(int page, int size) {
        if (page < 0 || size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                    "page는 0 이상, size는 1 이상 100 이하여야 합니다."
            );
        }
    }

    private record DeletedObject(String bucket, String objectKey) {
    }
}
