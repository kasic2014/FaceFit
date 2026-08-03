package com.facefit.backend.interview.integration;

public interface ContentAnalysisPort {

    PortResult<AnalysisResult> analyze(AnswerAnalysisRequest request);
}
