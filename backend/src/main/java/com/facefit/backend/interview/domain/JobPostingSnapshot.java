package com.facefit.backend.interview.domain;

import com.facefit.backend.jobposting.domain.JobPosting;

public record JobPostingSnapshot(
        String companyName,
        String targetRole,
        String mainResponsibilities,
        String qualifications,
        String preferredQualifications,
        String technologiesTools,
        String coreCompetencies,
        String companyBusinessIntro
) {

    public static JobPostingSnapshot from(JobPosting posting) {
        return new JobPostingSnapshot(
                posting.getCompanyName(),
                posting.getTargetRole(),
                posting.getMainResponsibilities(),
                posting.getQualifications(),
                posting.getPreferredQualifications(),
                posting.getTechnologiesTools(),
                posting.getCoreCompetencies(),
                posting.getCompanyBusinessIntro()
        );
    }
}
