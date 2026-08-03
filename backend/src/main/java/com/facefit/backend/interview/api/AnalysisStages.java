package com.facefit.backend.interview.api;

public record AnalysisStages(
        AnalysisStageStatus stt,
        AnalysisStageStatus cv,
        AnalysisStageStatus voice,
        AnalysisStageStatus content
) {
}
