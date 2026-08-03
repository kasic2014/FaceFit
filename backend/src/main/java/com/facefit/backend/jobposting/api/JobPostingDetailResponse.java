package com.facefit.backend.jobposting.api;

import com.facefit.backend.jobposting.domain.JobPosting;
import com.facefit.backend.jobposting.domain.JobPostingInputType;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;

import java.time.OffsetDateTime;
import java.util.UUID;

public record JobPostingDetailResponse(
        UUID jobPostingId,
        JobPostingInputType inputType,
        String originalFileName,
        JobPostingProcessingStatus processingStatus,
        String rawText,
        String extractedText,
        String companyName,
        String targetRole,
        String mainResponsibilities,
        String qualifications,
        String preferredQualifications,
        String technologiesTools,
        String coreCompetencies,
        String companyBusinessIntro,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt
) {
    public static JobPostingDetailResponse from(JobPosting posting) {
        return new JobPostingDetailResponse(
                posting.getJobPostingId(),
                posting.getInputType(),
                posting.getOriginalFileName(),
                posting.getProcessingStatus(),
                posting.getInputType() == JobPostingInputType.TEXT ? posting.getRawText() : null,
                posting.getInputType() == JobPostingInputType.FILE ? posting.getExtractedText() : null,
                posting.getCompanyName(),
                posting.getTargetRole(),
                posting.getMainResponsibilities(),
                posting.getQualifications(),
                posting.getPreferredQualifications(),
                posting.getTechnologiesTools(),
                posting.getCoreCompetencies(),
                posting.getCompanyBusinessIntro(),
                posting.getCreatedAt(),
                posting.getUpdatedAt()
        );
    }
}
