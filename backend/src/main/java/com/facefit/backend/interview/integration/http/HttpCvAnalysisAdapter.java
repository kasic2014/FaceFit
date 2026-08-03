package com.facefit.backend.interview.integration.http;

import com.facefit.backend.interview.integration.AnalysisResult;
import com.facefit.backend.interview.integration.AnswerAnalysisRequest;
import com.facefit.backend.interview.integration.CvAnalysisPort;
import com.facefit.backend.interview.integration.PortResult;
import org.springframework.stereotype.Component;

@Component
public final class HttpCvAnalysisAdapter implements CvAnalysisPort {

    private final FaceFitAiHttpClient client;
    private final AiMediaForwarder mediaForwarder;

    HttpCvAnalysisAdapter(
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
                media -> client.analyzeCv(
                        request.answerId(),
                        request.mimeType(),
                        media
                )
        );
    }
}
