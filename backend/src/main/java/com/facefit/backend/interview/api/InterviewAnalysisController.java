package com.facefit.backend.interview.api;

import com.facefit.backend.common.api.ApiResponse;
import com.facefit.backend.interview.application.IdempotentResult;
import com.facefit.backend.interview.application.InterviewAnalysisQueryService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/interview-sessions")
@RequiredArgsConstructor
public class InterviewAnalysisController {

    private final InterviewAnalysisQueryService service;

    @GetMapping("/{sessionId}/analysis-status")
    public ApiResponse<InterviewAnalysisStatusResponse> analysisStatus(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId
    ) {
        return ApiResponse.success(service.analysisStatus(jwt, sessionId));
    }

    @GetMapping("/{sessionId}/report")
    public ResponseEntity<ApiResponse<InterviewReportResponse>> report(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId
    ) {
        IdempotentResult<InterviewReportResponse> result =
                service.report(jwt, sessionId);
        return ResponseEntity
                .status(HttpStatusCode.valueOf(result.httpStatus()))
                .body(ApiResponse.success(result.body()));
    }
}
