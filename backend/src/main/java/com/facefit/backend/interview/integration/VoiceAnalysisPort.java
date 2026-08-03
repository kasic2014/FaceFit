package com.facefit.backend.interview.integration;

public interface VoiceAnalysisPort {

    PortResult<AnalysisResult> analyze(AnswerAnalysisRequest request);
}
