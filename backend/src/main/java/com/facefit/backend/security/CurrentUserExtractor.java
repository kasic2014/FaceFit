package com.facefit.backend.security;

import com.facefit.backend.common.exception.InvalidCurrentUserException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

import java.util.UUID;

@Component
public class CurrentUserExtractor {

    public CurrentUser extract(Jwt jwt) {
        if (jwt == null || !StringUtils.hasText(jwt.getSubject())) {
            throw new InvalidCurrentUserException("JWT sub claim이 필요합니다.");
        }

        UUID userId;
        try {
            userId = UUID.fromString(jwt.getSubject());
        } catch (IllegalArgumentException exception) {
            throw new InvalidCurrentUserException("JWT sub claim은 UUID 형식이어야 합니다.");
        }

        return new CurrentUser(
                userId,
                jwt.getClaimAsString("email"),
                jwt.getClaimAsString("role")
        );
    }
}
