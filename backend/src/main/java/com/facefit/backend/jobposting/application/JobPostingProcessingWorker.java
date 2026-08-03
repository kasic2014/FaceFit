package com.facefit.backend.jobposting.application;

import com.facefit.backend.common.exception.StorageOperationException;
import com.facefit.backend.jobposting.domain.JobPosting;
import com.facefit.backend.jobposting.domain.JobPostingInputType;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;
import com.facefit.backend.jobposting.domain.StructuredJobPosting;
import com.facefit.backend.jobposting.extraction.JobPostingTextExtractionService;
import com.facefit.backend.jobposting.repository.JobPostingRepository;
import com.facefit.backend.jobposting.storage.JobPostingStorage;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.OffsetDateTime;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class JobPostingProcessingWorker {

    public static final int MAX_PROCESSING_ATTEMPTS = 3;

    private final JobPostingRepository repository;
    private final JobPostingStorage storage;
    private final JobPostingTextExtractionService extractionService;
    private final JobPostingTextNormalizer normalizer;
    private final DeterministicJobPostingStructurer structurer;
    private final TransactionTemplate transactionTemplate;

    @Value("${facefit.job-postings.processing.stale-minutes:15}")
    private long staleMinutes;

    public void process(UUID jobPostingId) {
        for (int attempt = 0; attempt < MAX_PROCESSING_ATTEMPTS; attempt++) {
            ProcessingTarget target = claim(jobPostingId);
            if (target == null) {
                return;
            }
            try {
                String sourceText = sourceText(target);
                String extracted = normalizer.normalize(sourceText);
                if (extracted.isBlank()) {
                    throw new JobProcessingException("EXTRACTED_TEXT_EMPTY", false);
                }
                StructuredJobPosting structured = structurer.structure(extracted);
                if (structured.hasRequiredFields()) {
                    complete(target, extracted, structured);
                } else {
                    fail(target, extracted, structured, "STRUCTURED_FIELDS_INCOMPLETE");
                }
                return;
            } catch (StorageOperationException storageFailure) {
                if (!retryOrFail(target, new JobProcessingException(
                        "JOB_STORAGE_DOWNLOAD_FAILED",
                        true,
                        storageFailure
                ))) {
                    return;
                }
            } catch (JobProcessingException processingFailure) {
                if (!retryOrFail(target, processingFailure)) {
                    return;
                }
            } catch (RuntimeException unexpected) {
                log.error(
                        "Job posting processing failed unexpectedly type={}",
                        unexpected.getClass().getSimpleName()
                );
                fail(target, null, null, "JOB_PROCESSING_FAILED");
                return;
            }
        }
    }

    private String sourceText(ProcessingTarget target) {
        if (target.inputType() == JobPostingInputType.TEXT) {
            return target.rawText();
        }
        byte[] content = storage.download(target.storageBucket(), target.storagePath());
        return extractionService.extract(target.format(), content);
    }

    private ProcessingTarget claim(UUID jobPostingId) {
        return transactionTemplate.execute(status -> {
            JobPosting posting = repository.findByIdForUpdate(jobPostingId).orElse(null);
            if (posting == null) {
                return null;
            }
            OffsetDateTime now = OffsetDateTime.now();
            if (!posting.claimProcessing(
                    now,
                    now.minusMinutes(staleMinutes),
                    MAX_PROCESSING_ATTEMPTS
            )) {
                return null;
            }
            repository.saveAndFlush(posting);
            return new ProcessingTarget(
                    posting.getJobPostingId(),
                    posting.getInputType(),
                    posting.getRawText(),
                    posting.getStorageBucket(),
                    posting.getStoragePath(),
                    format(posting.getMimeType()),
                    posting.getProcessingAttemptCount()
            );
        });
    }

    private boolean retryOrFail(ProcessingTarget target, JobProcessingException failure) {
        if (failure.isRetryable() && target.processingAttempt() < MAX_PROCESSING_ATTEMPTS) {
            return releaseForRetry(target);
        }
        fail(target, null, null, failure.getErrorCode());
        return false;
    }

    private boolean releaseForRetry(ProcessingTarget target) {
        Boolean released = transactionTemplate.execute(status -> {
            JobPosting posting = repository.findByIdForUpdate(target.jobPostingId()).orElse(null);
            if (!isCurrentClaim(posting, target)) {
                return false;
            }
            posting.releaseForRetry();
            repository.saveAndFlush(posting);
            return true;
        });
        return Boolean.TRUE.equals(released);
    }

    private void complete(
            ProcessingTarget target,
            String extracted,
            StructuredJobPosting structured
    ) {
        transactionTemplate.executeWithoutResult(status -> {
            JobPosting posting = repository.findByIdForUpdate(target.jobPostingId()).orElse(null);
            if (!isCurrentClaim(posting, target)) {
                return;
            }
            posting.complete(extracted, structured, OffsetDateTime.now());
            repository.saveAndFlush(posting);
        });
    }

    private void fail(
            ProcessingTarget target,
            String extracted,
            StructuredJobPosting structured,
            String errorCode
    ) {
        transactionTemplate.executeWithoutResult(status -> {
            JobPosting posting = repository.findByIdForUpdate(target.jobPostingId()).orElse(null);
            if (!isCurrentClaim(posting, target)) {
                return;
            }
            posting.fail(extracted, structured, errorCode, OffsetDateTime.now());
            repository.saveAndFlush(posting);
        });
    }

    private boolean isCurrentClaim(JobPosting posting, ProcessingTarget target) {
        return posting != null
                && posting.getDeletedAt() == null
                && posting.getProcessingStatus() == JobPostingProcessingStatus.PROCESSING
                && posting.getProcessingAttemptCount() == target.processingAttempt()
                && posting.getProcessingStartedAt() != null;
    }

    private JobPostingFileFormat format(String mimeType) {
        if (mimeType == null) {
            return null;
        }
        return switch (mimeType) {
            case JobPostingFileValidator.PDF_MIME -> JobPostingFileFormat.PDF;
            case JobPostingFileValidator.DOCX_MIME -> JobPostingFileFormat.DOCX;
            case JobPostingFileValidator.JPEG_MIME -> JobPostingFileFormat.JPEG;
            case JobPostingFileValidator.PNG_MIME -> JobPostingFileFormat.PNG;
            case JobPostingFileValidator.HWP5_MIME -> JobPostingFileFormat.HWP5;
            default -> throw new JobProcessingException("FILE_TYPE_NOT_SUPPORTED", false);
        };
    }

    private record ProcessingTarget(
            UUID jobPostingId,
            JobPostingInputType inputType,
            String rawText,
            String storageBucket,
            String storagePath,
            JobPostingFileFormat format,
            int processingAttempt
    ) {
    }
}
