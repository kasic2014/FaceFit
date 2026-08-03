package com.facefit.backend.jobposting.application;

import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        name = "facefit.job-postings.processing.async-enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class JobPostingProcessingListener {

    private final JobPostingProcessingWorker worker;

    @Async("jobPostingExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterRegistration(JobPostingRegisteredEvent event) {
        worker.process(event.jobPostingId());
    }
}
