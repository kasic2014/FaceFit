package com.facefit.backend.security;

import com.facefit.backend.member.application.CurrentProfileService;
import com.facefit.backend.member.domain.MemberStatus;
import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.member.repository.ProfileRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.Optional;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "DB_URL=jdbc:postgresql://localhost:5432/facefit",
        "DB_USERNAME=test",
        "DB_PASSWORD=test",
        "SUPABASE_JWT_ISSUER_URI=https://test-project.supabase.co/auth/v1",
        "FLYWAY_ENABLED=false",
        "spring.autoconfigure.exclude="
                + "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,"
                + "org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration,"
                + "org.springframework.boot.autoconfigure.flyway.FlywayAutoConfiguration"
})
@AutoConfigureMockMvc
class SecurityIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @MockitoBean
    private CurrentProfileService currentProfileService;

    private ProfileRepository profileRepository;

    @BeforeEach
    void setUpCurrentProfileService() {
        profileRepository = mock(ProfileRepository.class);
        CurrentProfileService delegate = new CurrentProfileService(
                new CurrentUserExtractor(),
                profileRepository
        );
        when(currentProfileService.getOrCreateCurrentProfile(any()))
                .thenAnswer(invocation -> delegate.getOrCreateCurrentProfile(invocation.getArgument(0)));
    }

    @Test
    void authMeWithoutTokenReturnsUnauthorized() throws Exception {
        mockMvc.perform(get("/api/v1/auth/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(content().contentTypeCompatibleWith("application/json"))
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));
    }

    @Test
    void actuatorHealthIsPublic() throws Exception {
        mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("UP"));
    }

    @Test
    void authMeRejectsNonUuidSubject() throws Exception {
        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token
                                .subject("not-a-uuid")
                                .claim("role", "authenticated"))))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.error.code").value("INVALID_AUTHENTICATED_USER"));
    }

    @Test
    void authMeRejectsMissingSubject() throws Exception {
        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token.claim("sub", ""))))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.error.code").value("INVALID_AUTHENTICATED_USER"));
    }

    @Test
    void authMeReturnsProfileStateFromVerifiedJwt() throws Exception {
        UUID userId = UUID.randomUUID();
        Profile profile = profile(
                userId,
                MemberStatus.ACTIVE,
                OnboardingStatus.NOT_STARTED
        );
        when(profileRepository.findById(userId)).thenReturn(Optional.of(profile));

        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token
                                .subject(userId.toString())
                                .claim("email", "user@example.com")
                                .claim("role", "authenticated"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.userId").value(userId.toString()))
                .andExpect(jsonPath("$.data.memberStatus").value("ACTIVE"))
                .andExpect(jsonPath("$.data.onboardingStatus").value("NOT_STARTED"))
                .andExpect(jsonPath("$.data.email").doesNotExist())
                .andExpect(jsonPath("$.data.role").doesNotExist())
                .andExpect(jsonPath("$.data.createdAt").doesNotExist());
    }

    @Test
    void authMeReturnsCurrentStateForInactiveMember() throws Exception {
        UUID userId = UUID.randomUUID();
        Profile profile = profile(
                userId,
                MemberStatus.BLOCKED,
                OnboardingStatus.IN_PROGRESS
        );
        when(profileRepository.findById(userId)).thenReturn(Optional.of(profile));

        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.memberStatus").value("BLOCKED"))
                .andExpect(jsonPath("$.data.onboardingStatus").value("IN_PROGRESS"));
    }

    private Profile profile(
            UUID userId,
            MemberStatus memberStatus,
            OnboardingStatus onboardingStatus
    ) {
        Profile profile = mock(Profile.class);
        when(profile.getUserId()).thenReturn(userId);
        when(profile.getMemberStatus()).thenReturn(memberStatus);
        when(profile.getOnboardingStatus()).thenReturn(onboardingStatus);
        return profile;
    }
}
