package com.facefit.backend.jobposting.api;

import com.facefit.backend.common.api.ApiResponse;
import com.facefit.backend.common.api.PageResponse;
import com.facefit.backend.jobposting.application.JobPostingService;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/job-postings")
@RequiredArgsConstructor
public class JobPostingController {

    private final JobPostingService service;

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ApiResponse<JobPostingCreatedResponse> createFile(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(required = false) String inputType,
            @RequestPart(required = false) MultipartFile file,
            @RequestParam(required = false) String rawText
    ) {
        return ApiResponse.success(JobPostingCreatedResponse.from(
                service.createFile(jwt, inputType, file, rawText)
        ));
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ApiResponse<JobPostingCreatedResponse> createText(
            @AuthenticationPrincipal Jwt jwt,
            @RequestBody JobPostingTextCreateRequest request
    ) {
        return ApiResponse.success(JobPostingCreatedResponse.from(
                service.createText(jwt, request.inputType(), request.rawText())
        ));
    }

    @GetMapping
    public ApiResponse<PageResponse<JobPostingSummaryResponse>> findAll(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(required = false) JobPostingProcessingStatus processingStatus,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size
    ) {
        return ApiResponse.success(service.findAll(jwt, processingStatus, page, size));
    }

    @GetMapping("/{jobPostingId}")
    public ApiResponse<JobPostingDetailResponse> findOne(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID jobPostingId
    ) {
        return ApiResponse.success(service.findOne(jwt, jobPostingId));
    }

    @PatchMapping(
            path = "/{jobPostingId}",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ApiResponse<JobPostingDetailResponse> patch(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID jobPostingId,
            @RequestBody JobPostingPatchRequest request
    ) {
        return ApiResponse.success(service.patch(jwt, jobPostingId, request));
    }

    @DeleteMapping("/{jobPostingId}")
    public ResponseEntity<Void> delete(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID jobPostingId
    ) {
        service.delete(jwt, jobPostingId);
        return ResponseEntity.noContent().build();
    }
}
