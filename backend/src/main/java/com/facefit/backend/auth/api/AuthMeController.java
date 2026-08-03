package com.facefit.backend.auth.api;

import com.facefit.backend.common.api.ApiResponse;
import com.facefit.backend.config.OpenApiConfig;
import com.facefit.backend.member.application.CurrentProfileService;
import com.facefit.backend.member.domain.Profile;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "Authentication")
@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
public class AuthMeController {

    private final CurrentProfileService currentProfileService;

    @Operation(
            summary = "현재 인증 회원 상태 확인",
            description = "검증된 Supabase Access Token의 sub로 프로필을 조회하거나 최초 생성하고 현재 상태를 반환합니다."
    )
    @SecurityRequirement(name = OpenApiConfig.BEARER_AUTH)
    @GetMapping("/me")
    public ApiResponse<AuthMeResponse> me(@AuthenticationPrincipal Jwt jwt) {
        Profile profile = currentProfileService.getOrCreateCurrentProfile(jwt);
        return ApiResponse.success(AuthMeResponse.from(profile));
    }
}
