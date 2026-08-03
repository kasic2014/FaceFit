package com.facefit.backend.interview.integration.http;

import com.facefit.backend.interview.integration.AnalysisResult;
import com.facefit.backend.interview.integration.AnswerAnalysisRequest;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.integration.VoiceAnalysisPort;
import org.springframework.stereotype.Component;

@Component
public final class HttpVoiceAnalysisAdapter implements VoiceAnalysisPort {

    private final FaceFitAiHttpClient client;
    private final AiMediaForwarder mediaForwarder;

    HttpVoiceAnalysisAdapter(
            FaceFitAiHttpClient client,
            AiMediaForwarder mediaForwarder
    ) {
        this.client = client;
        this.mediaForwarder = mediaForwarder;
    }

    @Override
    public PortResult<AnalysisResult> analyze(AnswerAnalysisRequest request) {
        return mediaForwarder.forward(
                request,
                media -> client.analyzeVoice(
                        request.answerId(),
                        request.mimeType(),
                        media
                )
        );
    }
}
