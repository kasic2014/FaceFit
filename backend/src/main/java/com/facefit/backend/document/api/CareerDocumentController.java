package com.facefit.backend.document.api;

import com.facefit.backend.common.api.ApiResponse;
import com.facefit.backend.common.api.PageResponse;
import com.facefit.backend.document.application.CareerDocumentService;
import com.facefit.backend.document.domain.CareerDocument;
import com.facefit.backend.document.domain.CareerDocumentType;
import com.facefit.backend.document.domain.DocumentProcessingStatus;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import java.util.UUID;

@RestController
@RequestMapping("/api/v1/career-documents")
@RequiredArgsConstructor
public class CareerDocumentController {

    private final CareerDocumentService careerDocumentService;

    @PostMapping(consumes = "multipart/form-data")
    public ApiResponse<CareerDocumentCreatedResponse> create(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam CareerDocumentType documentType,
            @RequestPart MultipartFile file
    ) {
        return ApiResponse.success(CareerDocumentCreatedResponse.from(
                careerDocumentService.create(jwt, documentType, file)
        ));
    }

    @GetMapping
    public ApiResponse<PageResponse<CareerDocumentResponse>> findAll(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(required = false) CareerDocumentType documentType,
            @RequestParam(required = false) DocumentProcessingStatus status,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size
    ) {
        return ApiResponse.success(
                careerDocumentService.findAll(jwt, documentType, status, page, size)
        );
    }

    @GetMapping("/{documentId}")
    public ApiResponse<CareerDocumentResponse> findOne(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID documentId
    ) {
        CareerDocument document = careerDocumentService.findOne(jwt, documentId);
        return ApiResponse.success(CareerDocumentResponse.from(document));
    }

    @DeleteMapping("/{documentId}")
    public ResponseEntity<Void> delete(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID documentId
    ) {
        careerDocumentService.delete(jwt, documentId);
        return ResponseEntity.noContent().build();
    }
}
