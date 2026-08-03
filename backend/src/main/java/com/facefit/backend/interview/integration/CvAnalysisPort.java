package com.facefit.backend.interview.integration;

public interface CvAnalysisPort {

    PortResult<AnalysisResult> analyze(AnswerAnalysisRequest request);
}
