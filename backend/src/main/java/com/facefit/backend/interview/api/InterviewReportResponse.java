package com.facefit.backend.interview.api;

import com.facefit.backend.interview.domain.InterviewSessionStatus;

import java.util.UUID;

public record InterviewReportResponse(
        UUID sessionId,
        InterviewSessionStatus sessionStatus,
        String reportStatus,
        InterviewReportData report
) {
}
