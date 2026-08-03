package com.facefit.backend.onboarding;

import com.facefit.backend.common.exception.MemberAccessDeniedException;
import com.facefit.backend.common.exception.OnboardingRequiredException;
import com.facefit.backend.member.domain.MemberStatus;
import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.member.repository.ProfileRepository;
import com.facefit.backend.onboarding.application.OnboardingService;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
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
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
class OnboardingIntegrationTest {

    private static final String ONBOARDING_URI = "/api/v1/members/me/onboarding";

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
    private OnboardingService onboardingService;

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
    void getCurrentOnboardingReturnsStateWithoutChangingIt() {
        UUID userId = insertProfile(MemberStatus.ACTIVE, OnboardingStatus.NOT_STARTED, null);

        Profile result = onboardingService.getCurrentOnboarding(verifiedJwt(userId));
        entityManager.clear();
        Profile reloaded = profileRepository.findById(userId).orElseThrow();

        assertThat(result.getOnboardingStatus()).isEqualTo(OnboardingStatus.NOT_STARTED);
        assertThat(result.getOnboardingCompletedAt()).isNull();
        assertThat(reloaded.getOnboardingStatus()).isEqualTo(OnboardingStatus.NOT_STARTED);
        assertThat(reloaded.getOnboardingCompletedAt()).isNull();
    }

    @ParameterizedTest
    @EnumSource(value = OnboardingStatus.class, names = {"NOT_STARTED", "IN_PROGRESS"})
    void completeCurrentOnboardingCompletesAllowedState(OnboardingStatus initialStatus) {
        UUID userId = insertProfile(MemberStatus.ACTIVE, initialStatus, null);

        Profile completed = onboardingService.completeCurrentOnboarding(verifiedJwt(userId));
        entityManager.clear();
        Profile reloaded = profileRepository.findById(userId).orElseThrow();

        assertThat(completed.getOnboardingStatus()).isEqualTo(OnboardingStatus.COMPLETED);
        assertThat(completed.getOnboardingCompletedAt()).isNotNull();
        assertThat(reloaded.getOnboardingStatus()).isEqualTo(OnboardingStatus.COMPLETED);
        assertThat(reloaded.getOnboardingCompletedAt()).isNotNull();
        assertThat(reloaded.getMemberStatus()).isEqualTo(MemberStatus.ACTIVE);
    }

    @Test
    void repeatedCompletionKeepsFirstCompletionTime() {
        UUID userId = insertProfile(MemberStatus.ACTIVE, OnboardingStatus.NOT_STARTED, null);

        Profile first = onboardingService.completeCurrentOnboarding(verifiedJwt(userId));
        Instant firstCompletedAt = first.getOnboardingCompletedAt().toInstant();
        Profile second = onboardingService.completeCurrentOnboarding(verifiedJwt(userId));

        assertThat(second.getOnboardingStatus()).isEqualTo(OnboardingStatus.COMPLETED);
        assertThat(second.getOnboardingCompletedAt().toInstant()).isEqualTo(firstCompletedAt);
    }

    @Test
    void concurrentCompletionChoosesExactlyOneCompletionTime() throws Exception {
        UUID userId = insertProfile(MemberStatus.ACTIVE, OnboardingStatus.IN_PROGRESS, null);
        Jwt jwt = verifiedJwt(userId);
        int requestCount = 8;
        ExecutorService executor = Executors.newFixedThreadPool(requestCount);
        CountDownLatch ready = new CountDownLatch(requestCount);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Instant>> results = new ArrayList<>();

        try {
            for (int index = 0; index < requestCount; index++) {
                results.add(executor.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("동시 완료 요청 시작 대기 시간이 초과되었습니다.");
                    }
                    return onboardingService.completeCurrentOnboarding(jwt)
                            .getOnboardingCompletedAt()
                            .toInstant();
                }));
            }

            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            List<Instant> completionTimes = new ArrayList<>();
            for (Future<Instant> result : results) {
                completionTimes.add(result.get(20, TimeUnit.SECONDS));
            }
            assertThat(completionTimes).containsOnly(completionTimes.getFirst());
        } finally {
            executor.shutdownNow();
        }

        Profile reloaded = profileRepository.findById(userId).orElseThrow();
        assertThat(reloaded.getOnboardingStatus()).isEqualTo(OnboardingStatus.COMPLETED);
        assertThat(reloaded.getOnboardingCompletedAt()).isNotNull();
    }

    @Test
    void requireCompletedOnboardingAllowsCompletedMember() {
        OffsetDateTime rawCompletedAt = OffsetDateTime.now().minusHours(1);
        OffsetDateTime completedAt = rawCompletedAt.withNano(
                rawCompletedAt.getNano() / 1_000 * 1_000
        );
        UUID userId = insertProfile(
                MemberStatus.ACTIVE,
                OnboardingStatus.COMPLETED,
                completedAt
        );

        Profile result = onboardingService.requireCompletedOnboarding(verifiedJwt(userId));

        assertThat(result.getUserId()).isEqualTo(userId);
        assertThat(result.getOnboardingStatus()).isEqualTo(OnboardingStatus.COMPLETED);
        assertThat(result.getOnboardingCompletedAt().toInstant())
                .isEqualTo(completedAt.toInstant());
    }

    @ParameterizedTest
    @EnumSource(value = OnboardingStatus.class, names = {"NOT_STARTED", "IN_PROGRESS"})
    void requireCompletedOnboardingRejectsIncompleteMember(OnboardingStatus onboardingStatus) {
        UUID userId = insertProfile(MemberStatus.ACTIVE, onboardingStatus, null);

        assertThatThrownBy(() ->
                onboardingService.requireCompletedOnboarding(verifiedJwt(userId))
        ).isInstanceOf(OnboardingRequiredException.class);
    }

    @ParameterizedTest
    @EnumSource(value = MemberStatus.class, names = {"BLOCKED", "WITHDRAWN"})
    void everyOnboardingOperationRejectsInactiveMember(MemberStatus memberStatus) {
        UUID userId = insertProfile(memberStatus, OnboardingStatus.NOT_STARTED, null);
        Jwt jwt = verifiedJwt(userId);

        assertThatThrownBy(() -> onboardingService.getCurrentOnboarding(jwt))
                .isInstanceOf(MemberAccessDeniedException.class);
        assertThatThrownBy(() -> onboardingService.completeCurrentOnboarding(jwt))
                .isInstanceOf(MemberAccessDeniedException.class);
        assertThatThrownBy(() -> onboardingService.requireCompletedOnboarding(jwt))
                .isInstanceOf(MemberAccessDeniedException.class);

        Profile unchanged = profileRepository.findById(userId).orElseThrow();
        assertThat(unchanged.getMemberStatus()).isEqualTo(memberStatus);
        assertThat(unchanged.getOnboardingStatus()).isEqualTo(OnboardingStatus.NOT_STARTED);
    }

    @Test
    void completingOneMemberDoesNotChangeAnotherMember() {
        UUID currentUserId = insertProfile(
                MemberStatus.ACTIVE,
                OnboardingStatus.NOT_STARTED,
                null
        );
        UUID otherUserId = insertProfile(
                MemberStatus.ACTIVE,
                OnboardingStatus.IN_PROGRESS,
                null
        );

        onboardingService.completeCurrentOnboarding(verifiedJwt(currentUserId));

        Profile current = profileRepository.findById(currentUserId).orElseThrow();
        Profile other = profileRepository.findById(otherUserId).orElseThrow();
        assertThat(current.getOnboardingStatus()).isEqualTo(OnboardingStatus.COMPLETED);
        assertThat(other.getOnboardingStatus()).isEqualTo(OnboardingStatus.IN_PROGRESS);
        assertThat(other.getOnboardingCompletedAt()).isNull();
    }

    @Test
    void databaseRejectsEveryStatusAndCompletionTimeMismatch() {
        UUID incompleteUserId = insertAuthUser();
        UUID completedUserId = insertAuthUser();

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO profiles (
                    user_id,
                    onboarding_status,
                    onboarding_completed_at
                ) VALUES (?, 'IN_PROGRESS', CURRENT_TIMESTAMP)
                """,
                incompleteUserId
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO profiles (
                    user_id,
                    onboarding_status,
                    onboarding_completed_at
                ) VALUES (?, 'COMPLETED', NULL)
                """,
                completedUserId
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void onboardingEndpointRequiresAuthentication() throws Exception {
        mockMvc.perform(patch(ONBOARDING_URI)
                        .contentType("application/json")
                        .content("{\"legalActions\":[]}"))
                .andExpect(status().isUnauthorized())
                .andExpect(content().contentTypeCompatibleWith("application/json"))
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));
    }

    @Test
    void onboardingEndpointCompletesActiveMemberWithCommonResponse() throws Exception {
        UUID userId = insertProfile(
                MemberStatus.ACTIVE,
                OnboardingStatus.NOT_STARTED,
                null
        );

        mockMvc.perform(patch(ONBOARDING_URI)
                        .with(jwt().jwt(token -> token.subject(userId.toString())))
                        .contentType("application/json")
                        .content("{\"legalActions\":[]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.onboardingStatus").value("COMPLETED"))
                .andExpect(jsonPath("$.data.onboardingCompletedAt").isNotEmpty())
                .andExpect(jsonPath("$.data.voiceAnalysisConsent").value(false))
                .andExpect(jsonPath("$.data.voiceAnalysisConsentedAt").doesNotExist())
                .andExpect(jsonPath("$.data.nextAction").value("GO_TO_SERVICE"))
                .andExpect(jsonPath("$.data.userId").doesNotExist())
                .andExpect(jsonPath("$.data.memberStatus").doesNotExist())
                .andExpect(jsonPath("$.data.createdAt").doesNotExist())
                .andExpect(jsonPath("$.timestamp").isNotEmpty());
    }

    @Test
    void voiceAnalysisConsentIsOptionalAndStoredWhenSelected() throws Exception {
        UUID userId = insertProfile(
                MemberStatus.ACTIVE,
                OnboardingStatus.NOT_STARTED,
                null
        );

        mockMvc.perform(patch(ONBOARDING_URI)
                        .with(jwt().jwt(token -> token.subject(userId.toString())))
                        .contentType("application/json")
                        .content("{\"legalActions\":[],\"voiceAnalysisConsent\":true}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.onboardingStatus").value("COMPLETED"))
                .andExpect(jsonPath("$.data.voiceAnalysisConsent").value(true))
                .andExpect(jsonPath("$.data.voiceAnalysisConsentedAt").isNotEmpty());

        Boolean consent = jdbcTemplate.queryForObject(
                "SELECT voice_analysis_consent FROM profiles WHERE user_id = ?",
                Boolean.class,
                userId
        );
        OffsetDateTime consentedAt = jdbcTemplate.queryForObject(
                "SELECT voice_analysis_consented_at FROM profiles WHERE user_id = ?",
                OffsetDateTime.class,
                userId
        );
        assertThat(consent).isTrue();
        assertThat(consentedAt).isNotNull();
    }

    @Test
    void onboardingEndpointReturnsForbiddenForInactiveMember() throws Exception {
        UUID userId = insertProfile(
                MemberStatus.BLOCKED,
                OnboardingStatus.NOT_STARTED,
                null
        );

        mockMvc.perform(patch(ONBOARDING_URI)
                        .with(jwt().jwt(token -> token.subject(userId.toString())))
                        .contentType("application/json")
                        .content("{\"legalActions\":[]}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.success").value(false))
                .andExpect(jsonPath("$.error.code").value("MEMBER_ACCESS_DENIED"));
    }

    @Test
    void authMeReturnsCompletedStatusAfterOnboardingCompletion() throws Exception {
        UUID userId = insertProfile(
                MemberStatus.ACTIVE,
                OnboardingStatus.NOT_STARTED,
                null
        );

        mockMvc.perform(patch(ONBOARDING_URI)
                        .with(jwt().jwt(token -> token.subject(userId.toString())))
                        .contentType("application/json")
                        .content("{\"legalActions\":[]}"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.userId").value(userId.toString()))
                .andExpect(jsonPath("$.data.onboardingStatus").value("COMPLETED"))
                .andExpect(jsonPath("$.data.nextAction").value("GO_TO_SERVICE"));
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

    private UUID insertProfile(
            MemberStatus memberStatus,
            OnboardingStatus onboardingStatus,
            OffsetDateTime onboardingCompletedAt
    ) {
        UUID userId = insertAuthUser();
        jdbcTemplate.update(
                """
                INSERT INTO profiles (
                    user_id,
                    member_status,
                    onboarding_status,
                    onboarding_completed_at
                ) VALUES (?, ?, ?, ?)
                """,
                userId,
                memberStatus.name(),
                onboardingStatus.name(),
                onboardingCompletedAt
        );
        return userId;
    }

    private UUID insertAuthUser() {
        UUID userId = UUID.randomUUID();
        jdbcTemplate.update("INSERT INTO auth.users (id) VALUES (?)", userId);
        return userId;
    }
}
