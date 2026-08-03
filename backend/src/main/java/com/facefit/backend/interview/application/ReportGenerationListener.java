package com.facefit.backend.interview.application;

import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        name = "facefit.interview.processing.dispatch-enabled",
        havingValue = "true"
)
public class ReportGenerationListener {

    private final ReportGenerationWorker worker;

    @Async("interviewProcessingExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterRequested(ReportGenerationRequestedEvent event) {
        worker.process(event.jobId());
    }
}
