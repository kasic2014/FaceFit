package com.facefit.backend.interview.application;

import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.repository.InterviewProcessingJobRepository;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        name = "facefit.interview.processing.recovery-enabled",
        havingValue = "true"
)
public class InterviewProcessingRecoveryScheduler {

    private final InterviewProcessingJobRepository repository;
    private final InterviewSessionRepository sessionRepository;
    private final QuestionGenerationWorker questionWorker;
    private final AnswerAnalysisWorker answerWorker;
    private final ReportGenerationWorker reportWorker;
    private final InterviewAnalysisOrchestrator orchestrator;

    @Async("interviewProcessingExecutor")
    @Scheduled(
            initialDelayString =
                    "${facefit.interview.processing.recovery-initial-delay-ms:10000}",
            fixedDelayString =
                    "${facefit.interview.processing.recovery-delay-ms:10000}"
    )
    public void recover() {
        for (UUID jobId : repository.findDueJobIds(
                60,
                20
        )) {
            InterviewJobType type = repository.findById(jobId)
                    .map(job -> job.getType())
                    .orElse(null);
            if (type == InterviewJobType.QUESTION_GENERATION) {
                questionWorker.process(jobId);
            } else if (type == InterviewJobType.REPORT_GENERATION) {
                reportWorker.process(jobId);
            } else if (type != null) {
                answerWorker.process(jobId);
            }
        }
        for (UUID sessionId : sessionRepository.findAnalysisCandidateIds(20)) {
            orchestrator.orchestrate(sessionId);
        }
    }
}
