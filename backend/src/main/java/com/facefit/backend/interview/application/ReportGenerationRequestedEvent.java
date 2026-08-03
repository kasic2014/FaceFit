package com.facefit.backend.interview.application;

import java.util.UUID;

public record ReportGenerationRequestedEvent(UUID jobId) {
}
