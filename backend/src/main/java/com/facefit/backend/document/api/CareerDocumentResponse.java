package com.facefit.backend.document.api;

import com.facefit.backend.document.domain.CareerDocument;
import com.facefit.backend.document.domain.CareerDocumentType;
import com.facefit.backend.document.domain.DocumentProcessingStatus;

import java.time.OffsetDateTime;
import java.util.UUID;

public record CareerDocumentResponse(
        UUID documentId,
        CareerDocumentType documentType,
        String originalFileName,
        String mimeType,
        long fileSizeBytes,
        DocumentProcessingStatus status,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt
) {
    public static CareerDocumentResponse from(CareerDocument document) {
        return new CareerDocumentResponse(
                document.getDocumentId(),
                document.getDocumentType(),
                document.getOriginalFileName(),
                document.getMimeType(),
                document.getFileSizeBytes(),
                document.getProcessingStatus(),
                document.getCreatedAt(),
                document.getUpdatedAt()
        );
    }
}
