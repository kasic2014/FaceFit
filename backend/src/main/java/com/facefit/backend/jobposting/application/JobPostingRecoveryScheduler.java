package com.facefit.backend.jobposting.application;

import com.facefit.backend.jobposting.repository.JobPostingRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.task.TaskExecutor;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.OffsetDateTime;
import java.util.UUID;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        name = "facefit.job-postings.processing.recovery-enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class JobPostingRecoveryScheduler {

    private final JobPostingRepository repository;
    private final JobPostingProcessingWorker worker;
    @Qualifier("jobPostingExecutor")
    private final TaskExecutor taskExecutor;

    @Value("${facefit.job-postings.processing.stale-minutes:15}")
    private long staleMinutes;

    @Value("${facefit.job-postings.processing.recovery-batch-size:20}")
    private int batchSize;

    @Scheduled(
            initialDelayString = "${facefit.job-postings.processing.recovery-initial-delay-ms:60000}",
            fixedDelayString = "${facefit.job-postings.processing.recovery-delay-ms:60000}"
    )
    public void recoverStaleProcessingRows() {
        for (UUID jobPostingId : repository.findRecoverableIds(
                OffsetDateTime.now().minusMinutes(staleMinutes),
                JobPostingProcessingWorker.MAX_PROCESSING_ATTEMPTS,
                PageRequest.of(0, batchSize)
        )) {
            taskExecutor.execute(() -> worker.process(jobPostingId));
        }
    }
}
