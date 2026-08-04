package com.facefit.backend.interview.integration.http;

import com.facefit.backend.interview.domain.StorageProvider;
import com.facefit.backend.interview.integration.AnswerAnalysisRequest;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.storage.InterviewAnswerStorage;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiMediaForwarderTest {

    @Test
    void createsAFreshPresignedUrlForEveryWorkerAttempt() {
        InterviewAnswerStorage storage = mock(InterviewAnswerStorage.class);
        UUID answerId = UUID.randomUUID();
        when(storage.createPresignedGetUrl(
                StorageProvider.NCLOUD, "bucket", "sessions/key.mp4"
        )).thenReturn(
                URI.create("https://kr.object.ncloudstorage.com/bucket/key?X-Amz-Signature=one"),
                URI.create("https://kr.object.ncloudstorage.com/bucket/key?X-Amz-Signature=two")
        );
        AiMediaForwarder forwarder = new AiMediaForwarder(storage);
        AnswerAnalysisRequest request = new AnswerAnalysisRequest(
                answerId, UUID.randomUUID(), UUID.randomUUID(), "question",
                StorageProvider.NCLOUD, "bucket", "sessions/key.mp4",
                "video/mp4", 100, 30, 30_000, null
        );

        PortResult<String> first = forwarder.forward(
                request, url -> PortResult.success(url.getRawQuery())
        );
        PortResult<String> second = forwarder.forward(
                request, url -> PortResult.success(url.getRawQuery())
        );

        assertThat(((PortResult.Success<String>) first).value()).contains("one");
        assertThat(((PortResult.Success<String>) second).value()).contains("two");
        verify(storage, times(2)).createPresignedGetUrl(
                StorageProvider.NCLOUD, "bucket", "sessions/key.mp4"
        );
    }
}
