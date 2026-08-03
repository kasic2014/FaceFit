package com.facefit.backend.jobposting.application;

import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
public class JobPostingObjectKeyFactory {

    public String create(UUID verifiedUserId, UUID jobPostingId, String validatedExtension) {
        return "%s/%s/%s.%s".formatted(
                verifiedUserId,
                jobPostingId,
                UUID.randomUUID(),
                validatedExtension
        );
    }
}
