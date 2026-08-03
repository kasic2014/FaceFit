package com.facefit.backend.jobposting.api;

import com.facefit.backend.jobposting.domain.JobPosting;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;

import java.util.UUID;

public record JobPostingCreatedResponse(
        UUID jobPostingId,
        JobPostingProcessingStatus processingStatus
) {
    public static JobPostingCreatedResponse from(JobPosting posting) {
        return new JobPostingCreatedResponse(
                posting.getJobPostingId(),
                posting.getProcessingStatus()
        );
    }
}
