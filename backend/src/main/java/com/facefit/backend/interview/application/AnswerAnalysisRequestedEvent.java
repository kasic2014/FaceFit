package com.facefit.backend.interview.application;

import java.util.List;
import java.util.UUID;

public record AnswerAnalysisRequestedEvent(List<UUID> jobIds) {

    public AnswerAnalysisRequestedEvent {
        jobIds = List.copyOf(jobIds);
    }
}
