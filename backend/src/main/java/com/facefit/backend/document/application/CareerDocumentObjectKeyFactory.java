package com.facefit.backend.document.application;

import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
public class CareerDocumentObjectKeyFactory {

    public String create(UUID userId, UUID documentId, String extension) {
        return "%s/%s/%s.%s".formatted(
                userId,
                documentId,
                UUID.randomUUID(),
                extension
        );
    }
}
