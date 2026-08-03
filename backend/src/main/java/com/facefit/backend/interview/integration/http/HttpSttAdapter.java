package com.facefit.backend.interview.integration.http;

import com.facefit.backend.interview.integration.AnswerAnalysisRequest;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.integration.SttPort;
import com.facefit.backend.interview.integration.SttResult;
import org.springframework.stereotype.Component;

@Component
public final class HttpSttAdapter implements SttPort {

    private final FaceFitAiHttpClient client;
    private final AiMediaForwarder mediaForwarder;

    HttpSttAdapter(
            FaceFitAiHttpClient client,
            AiMediaForwarder mediaForwarder
    ) {
        this.client = client;
        this.mediaForwarder = mediaForwarder;
    }

    @Override
    public PortResult<SttResult> transcribe(AnswerAnalysisRequest request) {
        return mediaForwarder.forward(
                request,
                media -> client.transcribe(
                        request.answerId(),
                        request.mimeType(),
                        media
                )
        );
    }
}
