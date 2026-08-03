package com.facefit.backend.jobposting.api;

import com.facefit.backend.jobposting.domain.JobPosting;
import com.facefit.backend.jobposting.domain.JobPostingInputType;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;

import java.time.OffsetDateTime;
import java.util.UUID;

public record JobPostingSummaryResponse(
        UUID jobPostingId,
        JobPostingInputType inputType,
        String originalFileName,
        JobPostingProcessingStatus processingStatus,
        String companyName,
        String targetRole,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt
) {
    public static JobPostingSummaryResponse from(JobPosting posting) {
        return new JobPostingSummaryResponse(
                posting.getJobPostingId(),
                posting.getInputType(),
                posting.getOriginalFileName(),
                posting.getProcessingStatus(),
                posting.getCompanyName(),
                posting.getTargetRole(),
                posting.getCreatedAt(),
                posting.getUpdatedAt()
        );
    }
}
