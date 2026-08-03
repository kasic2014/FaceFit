package com.facefit.backend.interview;

import com.facefit.backend.interview.domain.InterviewAnswer;
import com.facefit.backend.interview.domain.InterviewJobType;
import com.facefit.backend.interview.domain.InterviewProcessingJob;
import com.facefit.backend.interview.domain.InterviewSession;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.time.OffsetDateTime;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

class InterviewProcessingJobOwnershipTest {

    @Test
    void staleWorkerCannotOverwriteResultAfterAReclaim() {
        InterviewProcessingJob job = InterviewProcessingJob.answerAnalysis(
                UUID.randomUUID(),
                mock(InterviewSession.class),
                mock(InterviewAnswer.class),
                InterviewJobType.CV
        );
        OffsetDateTime now = OffsetDateTime.now();
        UUID staleToken = UUID.randomUUID();
        UUID currentToken = UUID.randomUUID();

        assertThat(job.claim(staleToken, now, Duration.ofSeconds(60))).isTrue();
        assertThat(job.claim(
                currentToken,
                now.plusSeconds(61),
                Duration.ofSeconds(60)
        )).isTrue();
        assertThatThrownBy(() -> job.succeed(staleToken, null, now.plusSeconds(62)))
                .isInstanceOf(IllegalStateException.class);
        job.succeed(currentToken, null, now.plusSeconds(62));
        assertThat(job.getStatus().name()).isEqualTo("SUCCEEDED");
    }
}
