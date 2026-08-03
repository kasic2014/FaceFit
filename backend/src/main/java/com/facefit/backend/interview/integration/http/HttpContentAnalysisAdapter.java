package com.facefit.backend.interview.integration.http;

import com.facefit.backend.interview.integration.AnalysisResult;
import com.facefit.backend.interview.integration.AnswerAnalysisRequest;
import com.facefit.backend.interview.integration.ContentAnalysisPort;
import com.facefit.backend.interview.integration.PortResult;
import org.springframework.stereotype.Component;

@Component
public final class HttpContentAnalysisAdapter implements ContentAnalysisPort {

    private final FaceFitAiHttpClient client;

    HttpContentAnalysisAdapter(FaceFitAiHttpClient client) {
        this.client = client;
    }

    @Override
    public PortResult<AnalysisResult> analyze(AnswerAnalysisRequest request) {
        if (request == null) {
            return PortResult.permanentFailure("AI_REQUEST_INVALID");
        }
        return client.analyzeContent(
                request.answerId(),
                request.questionText(),
                request.transcript()
        );
    }
}
