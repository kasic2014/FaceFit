package com.facefit.backend.interview.application;

import java.util.UUID;

public record QuestionGenerationRequestedEvent(UUID jobId) {
}
