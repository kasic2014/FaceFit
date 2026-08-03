package com.facefit.backend.interview.api;

import com.facefit.backend.common.api.ApiResponse;
import com.facefit.backend.interview.application.InterviewSessionService;
import com.facefit.backend.interview.application.IdempotentResult;
import com.facefit.backend.interview.application.InterviewProgressService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/interview-sessions")
@RequiredArgsConstructor
public class InterviewSessionController {

    private final InterviewSessionService service;
    private final InterviewProgressService progressService;

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ApiResponse<InterviewSessionCreatedResponse> create(
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody InterviewSessionCreateRequest request
    ) {
        return ApiResponse.success(InterviewSessionCreatedResponse.from(
                service.create(jwt, request)
        ));
    }

    @GetMapping("/{sessionId}")
    public ApiResponse<InterviewSessionResponse> findOne(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId
    ) {
        return ApiResponse.success(service.findOne(jwt, sessionId));
    }

    @PatchMapping(
            path = "/{sessionId}",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ApiResponse<InterviewSessionResponse> patch(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId,
            @RequestBody InterviewSessionPatchRequest request
    ) {
        return ApiResponse.success(service.patch(jwt, sessionId, request));
    }

    @PostMapping("/{sessionId}/start")
    public ResponseEntity<ApiResponse<InterviewStartResponse>> start(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId,
            @RequestHeader(name = "Idempotency-Key", required = false)
            String idempotencyKey
    ) {
        IdempotentResult<InterviewStartResponse> result =
                progressService.start(jwt, sessionId, idempotencyKey);
        return ResponseEntity
                .status(HttpStatusCode.valueOf(result.httpStatus()))
                .body(ApiResponse.success(result.body()));
    }

    @GetMapping("/{sessionId}/questions/current")
    public ResponseEntity<ApiResponse<CurrentQuestionResponse>> currentQuestion(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId
    ) {
        IdempotentResult<CurrentQuestionResponse> result =
                progressService.currentQuestion(jwt, sessionId);
        return ResponseEntity
                .status(HttpStatusCode.valueOf(result.httpStatus()))
                .body(ApiResponse.success(result.body()));
    }

    @PostMapping(
            path = "/{sessionId}/completion",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<ApiResponse<InterviewCompletionResponse>> complete(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId,
            @RequestHeader(name = "Idempotency-Key", required = false)
            String idempotencyKey,
            @RequestBody InterviewCompletionRequest request
    ) {
        IdempotentResult<InterviewCompletionResponse> result =
                progressService.complete(jwt, sessionId, idempotencyKey, request);
        return ResponseEntity
                .status(HttpStatusCode.valueOf(result.httpStatus()))
                .body(ApiResponse.success(result.body()));
    }
}
