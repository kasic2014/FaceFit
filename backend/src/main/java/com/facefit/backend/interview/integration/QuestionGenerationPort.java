package com.facefit.backend.interview.integration;

public interface QuestionGenerationPort {

    PortResult<QuestionGenerationResponse> generate(QuestionGenerationRequest request);
}
