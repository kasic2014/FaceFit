package com.facefit.backend.security;

import java.util.UUID;

public record CurrentUser(
        UUID userId,
        String email,
        String role
) {
}
