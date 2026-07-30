package com.facefit.backend.onboarding.api;

import com.facefit.backend.common.api.ApiResponse;
import com.facefit.backend.config.OpenApiConfig;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.onboarding.application.OnboardingService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "Onboarding")
@RestController
@RequestMapping("/api/v1/members/me/onboarding")
@RequiredArgsConstructor
public class OnboardingController {

    private final OnboardingService onboardingService;

    @Operation(
            summary = "내 온보딩 완료",
            description = "ACTIVE 회원의 온보딩을 멱등하게 완료하고 최초 완료 일시를 반환합니다."
    )
    @SecurityRequirement(name = OpenApiConfig.BEARER_AUTH)
    @PatchMapping
    public ApiResponse<OnboardingResponse> complete(@AuthenticationPrincipal Jwt jwt) {
        Profile completed = onboardingService.completeCurrentOnboarding(jwt);
        return ApiResponse.success(OnboardingResponse.completed(completed));
    }
}
