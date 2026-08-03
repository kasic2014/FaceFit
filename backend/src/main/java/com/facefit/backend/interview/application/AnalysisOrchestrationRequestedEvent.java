package com.facefit.backend.interview.application;

import java.util.UUID;

public record AnalysisOrchestrationRequestedEvent(UUID sessionId) {
}
