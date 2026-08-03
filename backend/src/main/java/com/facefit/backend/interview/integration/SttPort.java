package com.facefit.backend.interview.integration;

public interface SttPort {

    PortResult<SttResult> transcribe(AnswerAnalysisRequest request);
}
