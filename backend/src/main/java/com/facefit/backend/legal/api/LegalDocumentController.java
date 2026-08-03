package com.facefit.backend.legal.api;

import com.facefit.backend.common.api.ApiResponse;
import com.facefit.backend.legal.application.LegalDocumentService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/v1/legal-documents")
@RequiredArgsConstructor
public class LegalDocumentController {

    private final LegalDocumentService legalDocumentService;

    @GetMapping
    public ApiResponse<List<LegalDocumentSummaryResponse>> findAll(
            @RequestParam(required = false) String type
    ) {
        return ApiResponse.success(legalDocumentService.findCurrentDocuments(type).stream()
                .map(LegalDocumentSummaryResponse::from)
                .toList());
    }

    @GetMapping("/{documentId}")
    public ApiResponse<LegalDocumentDetailResponse> findOne(
            @PathVariable UUID documentId
    ) {
        return ApiResponse.success(
                LegalDocumentDetailResponse.from(
                        legalDocumentService.findCurrentDocument(documentId)
                )
        );
    }
}
