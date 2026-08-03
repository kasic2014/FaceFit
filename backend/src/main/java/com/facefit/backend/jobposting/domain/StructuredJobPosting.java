package com.facefit.backend.jobposting.domain;

public record StructuredJobPosting(
        String companyName,
        String targetRole,
        String mainResponsibilities,
        String qualifications,
        String preferredQualifications,
        String technologiesTools,
        String coreCompetencies,
        String companyBusinessIntro
) {
    public boolean hasRequiredFields() {
        return hasText(companyName)
                && hasText(targetRole)
                && hasText(mainResponsibilities)
                && hasText(qualifications);
    }

    private static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
