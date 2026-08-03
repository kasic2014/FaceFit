package com.facefit.backend.interview.api;

import com.facefit.backend.common.api.ApiResponse;
import com.facefit.backend.interview.application.IdempotentResult;
import com.facefit.backend.interview.application.InterviewAnswerService;
import com.facefit.backend.interview.domain.AnswerEndedBy;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;

@RestController
@RequiredArgsConstructor
public class InterviewAnswerController {

    private final InterviewAnswerService service;

    @PostMapping(
            path = "/api/v1/interview-sessions/{sessionId}/answers",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<ApiResponse<InterviewAnswerCreatedResponse>> submit(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID sessionId,
            @RequestHeader(name = "Idempotency-Key", required = false)
            String idempotencyKey,
            @RequestParam(required = false) UUID questionId,
            @RequestPart(required = false) MultipartFile file,
            @RequestParam(required = false) Integer recordedDurationSec,
            @RequestParam(required = false) AnswerEndedBy endedBy
    ) {
        IdempotentResult<InterviewAnswerCreatedResponse> result = service.submit(
                jwt,
                sessionId,
                idempotencyKey,
                questionId,
                file,
                recordedDurationSec,
                endedBy
        );
        return ResponseEntity
                .status(HttpStatusCode.valueOf(result.httpStatus()))
                .body(ApiResponse.success(result.body()));
    }

    @GetMapping("/api/v1/interview-answers/{answerId}")
    public ApiResponse<InterviewAnswerResponse> findOne(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID answerId
    ) {
        return ApiResponse.success(service.findOne(jwt, answerId));
    }
}
