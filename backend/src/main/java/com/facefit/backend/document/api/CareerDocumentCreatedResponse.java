package com.facefit.backend.document.api;

import com.facefit.backend.document.domain.CareerDocument;
import com.facefit.backend.document.domain.CareerDocumentType;
import com.facefit.backend.document.domain.DocumentProcessingStatus;

import java.util.UUID;

public record CareerDocumentCreatedResponse(
        UUID documentId,
        CareerDocumentType documentType,
        DocumentProcessingStatus status
) {
    public static CareerDocumentCreatedResponse from(CareerDocument document) {
        return new CareerDocumentCreatedResponse(
                document.getDocumentId(),
                document.getDocumentType(),
                document.getProcessingStatus()
        );
    }
}
