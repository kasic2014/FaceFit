package com.facefit.backend.member;

import com.facefit.backend.common.exception.MemberAccessDeniedException;
import com.facefit.backend.common.exception.ProfileProvisioningException;
import com.facefit.backend.member.application.CurrentProfileService;
import com.facefit.backend.member.domain.MemberStatus;
import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.member.repository.ProfileRepository;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
class CurrentProfileIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRESQL =
            new PostgreSQLContainer<>(DockerImageName.parse("postgres:16-alpine"))
                    .withDatabaseName("facefit")
                    .withUsername("facefit")
                    .withPassword("facefit")
                    .withInitScript("db/test-init-auth.sql");

    @DynamicPropertySource
    static void registerDatabaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRESQL::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRESQL::getUsername);
        registry.add("spring.datasource.password", POSTGRESQL::getPassword);
        registry.add("spring.flyway.enabled", () -> true);
        registry.add("spring.jpa.hibernate.ddl-auto", () -> "validate");
        registry.add(
                "spring.security.oauth2.resourceserver.jwt.issuer-uri",
                () -> "https://test-project.supabase.co/auth/v1"
        );
    }

    @Autowired
    private CurrentProfileService currentProfileService;

    @Autowired
    private ProfileRepository profileRepository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private EntityManager entityManager;

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @BeforeEach
    void clearDatabase() {
        jdbcTemplate.execute(
                "TRUNCATE TABLE user_legal_records, legal_documents, profiles, auth.users CASCADE"
        );
        entityManager.clear();
    }

    @Test
    void firstRequestCreatesProfileWithJwtSubjectAndDatabaseDefaults() {
        UUID userId = insertAuthUser();

        Profile created = currentProfileService.getOrCreateCurrentProfile(verifiedJwt(userId));
        entityManager.clear();
        Profile reloaded = profileRepository.findById(userId).orElseThrow();

        assertThat(created.getUserId()).isEqualTo(userId);
        assertThat(reloaded.getUserId()).isEqualTo(userId);
        assertThat(reloaded.getMemberStatus()).isEqualTo(MemberStatus.ACTIVE);
        assertThat(reloaded.getOnboardingStatus()).isEqualTo(OnboardingStatus.NOT_STARTED);
        assertThat(reloaded.getOnboardingCompletedAt()).isNull();
        assertThat(reloaded.getCreatedAt()).isNotNull();
        assertThat(reloaded.getUpdatedAt()).isNotNull();
    }

    @Test
    void repeatedRequestsReturnSingleProfileWithoutChangingCreationTimeOrState() {
        UUID userId = insertAuthUser();

        Profile first = currentProfileService.getOrCreateCurrentProfile(verifiedJwt(userId));
        OffsetDateTime createdAt = first.getCreatedAt();
        Profile second = currentProfileService.getOrCreateCurrentProfile(verifiedJwt(userId));

        assertThat(second.getUserId()).isEqualTo(first.getUserId());
        assertThat(second.getCreatedAt()).isEqualTo(createdAt);
        assertThat(second.getMemberStatus()).isEqualTo(MemberStatus.ACTIVE);
        assertThat(second.getOnboardingStatus()).isEqualTo(OnboardingStatus.NOT_STARTED);
        assertThat(profileCount(userId)).isEqualTo(1);
    }

    @Test
    void existingProfileIsReturnedWithoutResettingMemberOrOnboardingState() {
        UUID userId = insertAuthUser();
        OffsetDateTime originalCreatedAt = OffsetDateTime.now()
                .minusDays(7)
                .withNano(123_000_000);
        jdbcTemplate.update(
                """
                INSERT INTO profiles (
                    user_id,
                    member_status,
                    onboarding_status,
                    created_at,
                    updated_at
                ) VALUES (?, 'BLOCKED', 'IN_PROGRESS', ?, ?)
                """,
                userId,
                originalCreatedAt,
                originalCreatedAt
        );

        Profile existing = currentProfileService.getOrCreateCurrentProfile(verifiedJwt(userId));

        assertThat(existing.getMemberStatus()).isEqualTo(MemberStatus.BLOCKED);
        assertThat(existing.getOnboardingStatus()).isEqualTo(OnboardingStatus.IN_PROGRESS);
        assertThat(existing.getCreatedAt().toInstant()).isEqualTo(originalCreatedAt.toInstant());
        assertThat(profileCount(userId)).isEqualTo(1);
    }

    @Test
    void requireActiveProfileAllowsActiveMember() {
        UUID userId = insertAuthUser();

        Profile profile = currentProfileService.requireActiveProfile(verifiedJwt(userId));

        assertThat(profile.getMemberStatus()).isEqualTo(MemberStatus.ACTIVE);
    }

    @ParameterizedTest
    @EnumSource(value = MemberStatus.class, names = {"BLOCKED", "WITHDRAWN"})
    void requireActiveProfileRejectsEveryInactiveMember(MemberStatus memberStatus) {
        UUID userId = insertAuthUser();
        jdbcTemplate.update(
                "INSERT INTO profiles (user_id, member_status) VALUES (?, ?)",
                userId,
                memberStatus.name()
        );

        assertThatThrownBy(() -> currentProfileService.requireActiveProfile(verifiedJwt(userId)))
                .isInstanceOf(MemberAccessDeniedException.class);
        assertThat(profileRepository.findById(userId).orElseThrow().getMemberStatus())
                .isEqualTo(memberStatus);
    }

    @Test
    void concurrentFirstRequestsCreateExactlyOneProfile() throws Exception {
        UUID userId = insertAuthUser();
        Jwt jwt = verifiedJwt(userId);
        int requestCount = 8;
        ExecutorService executor = Executors.newFixedThreadPool(requestCount);
        CountDownLatch ready = new CountDownLatch(requestCount);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<UUID>> results = new ArrayList<>();

        try {
            for (int index = 0; index < requestCount; index++) {
                results.add(executor.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("동시 요청 시작 대기 시간이 초과되었습니다.");
                    }
                    return currentProfileService.getOrCreateCurrentProfile(jwt).getUserId();
                }));
            }

            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            for (Future<UUID> result : results) {
                assertThat(result.get(20, TimeUnit.SECONDS)).isEqualTo(userId);
            }
        } finally {
            executor.shutdownNow();
        }

        assertThat(profileCount(userId)).isEqualTo(1);
    }

    @Test
    void missingSupabaseAuthUserFailsWithoutCreatingFakeOrPartialData() {
        UUID missingUserId = UUID.randomUUID();

        assertThatThrownBy(() ->
                currentProfileService.getOrCreateCurrentProfile(verifiedJwt(missingUserId))
        ).isInstanceOf(ProfileProvisioningException.class);

        assertThat(profileCount(missingUserId)).isZero();
        assertThat(authUserCount(missingUserId)).isZero();
    }

    @Test
    void authMeFirstAndRepeatedCallsCreateAndReturnTheSameProfile() throws Exception {
        UUID userId = insertAuthUser();

        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.userId").value(userId.toString()))
                .andExpect(jsonPath("$.data.memberStatus").value("ACTIVE"))
                .andExpect(jsonPath("$.data.onboardingStatus").value("NOT_STARTED"));

        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.userId").value(userId.toString()));

        assertThat(profileCount(userId)).isEqualTo(1);
    }

    @Test
    void authMeDoesNotHideInactiveMemberState() throws Exception {
        UUID userId = insertAuthUser();
        jdbcTemplate.update(
                "INSERT INTO profiles (user_id, member_status) VALUES (?, 'WITHDRAWN')",
                userId
        );

        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.memberStatus").value("WITHDRAWN"));
    }

    @Test
    void authMeReturnsSafeServerErrorWhenSupabaseAuthUserIsMissing() throws Exception {
        UUID missingUserId = UUID.randomUUID();

        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token.subject(missingUserId.toString()))))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.error.code").value("PROFILE_PROVISIONING_FAILED"))
                .andExpect(jsonPath("$.error.message")
                        .value("현재 사용자 프로필을 준비할 수 없습니다."))
                .andExpect(jsonPath("$.error.details").doesNotExist());

        assertThat(profileCount(missingUserId)).isZero();
    }

    private Jwt verifiedJwt(UUID userId) {
        Instant issuedAt = Instant.now();
        return Jwt.withTokenValue("verified-test-token")
                .header("alg", "none")
                .subject(userId.toString())
                .issuedAt(issuedAt)
                .expiresAt(issuedAt.plusSeconds(300))
                .build();
    }

    private UUID insertAuthUser() {
        UUID userId = UUID.randomUUID();
        jdbcTemplate.update("INSERT INTO auth.users (id) VALUES (?)", userId);
        return userId;
    }

    private int profileCount(UUID userId) {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM profiles WHERE user_id = ?",
                Integer.class,
                userId
        );
        return count == null ? 0 : count;
    }

    private int authUserCount(UUID userId) {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM auth.users WHERE id = ?",
                Integer.class,
                userId
        );
        return count == null ? 0 : count;
    }
}
