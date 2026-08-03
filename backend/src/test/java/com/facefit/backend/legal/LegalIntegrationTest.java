package com.facefit.backend.legal;

import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.onboarding.api.OnboardingRequest.LegalActionRequest;
import com.facefit.backend.onboarding.application.OnboardingService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
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

import static com.facefit.backend.legal.domain.LegalRecordActionType.ACKNOWLEDGED;
import static com.facefit.backend.legal.domain.LegalRecordActionType.CONSENTED;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
class LegalIntegrationTest {

    private static final String LEGAL_URI = "/api/v1/legal-documents";
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
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private OnboardingService onboardingService;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @BeforeEach
    void clearDatabase() {
        jdbcTemplate.execute(
                "TRUNCATE TABLE user_legal_records, legal_documents, profiles, auth.users CASCADE"
        );
    }

    @Test
    void listIsPublicAndReturnsOnlyCurrentEffectiveDocumentsInTypeOrder() throws Exception {
        UUID terms = insertDocument("TERMS", "CONSENT", "1.0", true, true, -1);
        UUID privacy = insertDocument("PRIVACY", "NOTICE", "1.0", true, true, -1);
        insertDocument("MARKETING", "CONSENT", "1.0", false, false, -1);
        insertDocument("FUTURE", "NOTICE", "1.0", true, true, 1);

        mockMvc.perform(get(LEGAL_URI))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.success").value(true))
                .andExpect(jsonPath("$.data.length()").value(2))
                .andExpect(jsonPath("$.data[0].documentId").value(privacy.toString()))
                .andExpect(jsonPath("$.data[0].type").value("PRIVACY"))
                .andExpect(jsonPath("$.data[0].requiredAction").value("NOTICE"))
                .andExpect(jsonPath("$.data[1].documentId").value(terms.toString()))
                .andExpect(jsonPath("$.data[1].content").doesNotExist())
                .andExpect(jsonPath("$.data[1].createdAt").doesNotExist());
    }

    @Test
    void listSupportsOptionalTypeFilterAndRejectsBlankFilter() throws Exception {
        insertDocument("TERMS", "CONSENT", "1.0", true, true, -1);
        insertDocument("PRIVACY", "NOTICE", "1.0", true, true, -1);

        mockMvc.perform(get(LEGAL_URI).queryParam("type", "TERMS"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.length()").value(1))
                .andExpect(jsonPath("$.data[0].type").value("TERMS"));

        mockMvc.perform(get(LEGAL_URI).queryParam("type", ""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
    }

    @Test
    void detailIsPublicAndHidesInternalColumns() throws Exception {
        UUID documentId = insertDocument("TERMS", "CONSENT", "1.0", true, true, -1);

        mockMvc.perform(get(LEGAL_URI + "/" + documentId))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.documentId").value(documentId.toString()))
                .andExpect(jsonPath("$.data.title").value("TERMS title"))
                .andExpect(jsonPath("$.data.content").value("TERMS content"))
                .andExpect(jsonPath("$.data.onboardingRequired").value(true))
                .andExpect(jsonPath("$.data.requiredAction").value("CONSENT"))
                .andExpect(jsonPath("$.data.effectiveAt").isNotEmpty())
                .andExpect(jsonPath("$.data.current").doesNotExist())
                .andExpect(jsonPath("$.data.createdAt").doesNotExist());
    }

    @Test
    void detailRejectsMissingNonCurrentAndFutureDocuments() throws Exception {
        UUID nonCurrent = insertDocument("OLD_TERMS", "CONSENT", "1.0", true, false, -1);
        UUID future = insertDocument("FUTURE_TERMS", "CONSENT", "1.0", true, true, 1);

        for (UUID documentId : List.of(UUID.randomUUID(), nonCurrent, future)) {
            mockMvc.perform(get(LEGAL_URI + "/" + documentId))
                    .andExpect(status().isNotFound())
                    .andExpect(jsonPath("$.error.code").value("LEGAL_DOCUMENT_NOT_FOUND"));
        }
    }

    @Test
    void onlyGetLegalRoutesArePublic() throws Exception {
        mockMvc.perform(post(LEGAL_URI))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(patch(ONBOARDING_URI)
                        .contentType("application/json")
                        .content("{\"legalActions\":[]}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void onboardingRecordsEveryRequiredActionAndCompletesAtomically() throws Exception {
        UUID userId = insertProfile();
        UUID terms = insertDocument("TERMS", "CONSENT", "1.0", true, true, -1);
        UUID privacy = insertDocument("PRIVACY", "NOTICE", "1.0", true, true, -1);

        mockMvc.perform(patch(ONBOARDING_URI)
                        .with(jwt().jwt(token -> token.subject(userId.toString())))
                        .contentType("application/json")
                        .content(requestJson(terms, "CONSENTED", privacy, "ACKNOWLEDGED")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.onboardingStatus").value("COMPLETED"))
                .andExpect(jsonPath("$.data.nextAction").value("GO_TO_SERVICE"));

        assertThat(recordCount(userId)).isEqualTo(2);
        assertThat(onboardingStatus(userId)).isEqualTo("COMPLETED");

        mockMvc.perform(get("/api/v1/auth/me")
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.onboardingStatus").value("COMPLETED"))
                .andExpect(jsonPath("$.data.nextAction").value("GO_TO_SERVICE"));
    }

    @Test
    void onboardingRejectsMissingPastUnknownAndWrongActionsWithoutPartialWrites() throws Exception {
        UUID userId = insertProfile();
        UUID terms = insertDocument("TERMS", "CONSENT", "2.0", true, true, -1);
        UUID privacy = insertDocument("PRIVACY", "NOTICE", "2.0", true, true, -1);
        UUID old = insertDocument("OLD_TERMS", "CONSENT", "1.0", true, false, -1);

        List<String> invalidRequests = List.of(
                requestJson(terms, "CONSENTED"),
                requestJson(terms, "CONSENTED", privacy, "CONSENTED"),
                requestJson(terms, "CONSENTED", old, "CONSENTED", privacy, "ACKNOWLEDGED"),
                requestJson(terms, "CONSENTED", UUID.randomUUID(), "ACKNOWLEDGED",
                        privacy, "ACKNOWLEDGED")
        );
        for (String body : invalidRequests) {
            mockMvc.perform(patch(ONBOARDING_URI)
                            .with(jwt().jwt(token -> token.subject(userId.toString())))
                            .contentType("application/json")
                            .content(body))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.error.code").value("INVALID_LEGAL_ACTIONS"));
            assertThat(recordCount(userId)).isZero();
            assertThat(onboardingStatus(userId)).isEqualTo("NOT_STARTED");
        }
    }

    @Test
    void repeatedAndConcurrentCompletionKeepsOneRecordAndFirstCompletionTime() throws Exception {
        UUID userId = insertProfile();
        UUID terms = insertDocument("TERMS", "CONSENT", "1.0", true, true, -1);
        Jwt token = verifiedJwt(userId);
        List<LegalActionRequest> actions = List.of(new LegalActionRequest(terms, CONSENTED));
        int requestCount = 6;
        ExecutorService executor = Executors.newFixedThreadPool(requestCount);
        CountDownLatch ready = new CountDownLatch(requestCount);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Instant>> results = new ArrayList<>();

        try {
            for (int index = 0; index < requestCount; index++) {
                results.add(executor.submit(() -> {
                    ready.countDown();
                    start.await(10, TimeUnit.SECONDS);
                    return onboardingService.completeCurrentOnboarding(token, actions)
                            .getOnboardingCompletedAt()
                            .toInstant();
                }));
            }
            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
            start.countDown();
            List<Instant> times = new ArrayList<>();
            for (Future<Instant> result : results) {
                times.add(result.get(20, TimeUnit.SECONDS));
            }
            assertThat(times).containsOnly(times.getFirst());
        } finally {
            executor.shutdownNow();
        }

        Instant firstTime = completionTime(userId);
        onboardingService.completeCurrentOnboarding(token, actions);
        assertThat(recordCount(userId)).isOne();
        assertThat(completionTime(userId)).isEqualTo(firstTime);
    }

    @Test
    void jwtSubjectAlwaysDeterminesRecordOwner() throws Exception {
        UUID currentUser = insertProfile();
        UUID otherUser = insertProfile();
        UUID terms = insertDocument("TERMS", "CONSENT", "1.0", true, true, -1);

        mockMvc.perform(patch(ONBOARDING_URI)
                        .with(jwt().jwt(token -> token.subject(currentUser.toString())))
                        .contentType("application/json")
                        .content(requestJson(terms, "CONSENTED")))
                .andExpect(status().isOk());

        assertThat(recordCount(currentUser)).isOne();
        assertThat(recordCount(otherUser)).isZero();
        assertThat(onboardingStatus(otherUser)).isEqualTo(OnboardingStatus.NOT_STARTED.name());
    }

    private UUID insertProfile() {
        UUID userId = UUID.randomUUID();
        jdbcTemplate.update("INSERT INTO auth.users (id) VALUES (?)", userId);
        jdbcTemplate.update("INSERT INTO profiles (user_id) VALUES (?)", userId);
        return userId;
    }

    private UUID insertDocument(
            String type,
            String legalAction,
            String version,
            boolean onboardingRequired,
            boolean current,
            int effectiveDayOffset
    ) {
        UUID documentId = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO legal_documents (
                    legal_document_id, document_type, legal_action_type, title,
                    version, content, is_onboarding_required, is_current, effective_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                documentId,
                type,
                legalAction,
                type + " title",
                version,
                type + " content",
                onboardingRequired,
                current,
                OffsetDateTime.now().plusDays(effectiveDayOffset)
        );
        return documentId;
    }

    private long recordCount(UUID userId) {
        return jdbcTemplate.queryForObject(
                "SELECT count(*) FROM user_legal_records WHERE user_id = ?",
                Long.class,
                userId
        );
    }

    private String onboardingStatus(UUID userId) {
        return jdbcTemplate.queryForObject(
                "SELECT onboarding_status FROM profiles WHERE user_id = ?",
                String.class,
                userId
        );
    }

    private Instant completionTime(UUID userId) {
        return jdbcTemplate.queryForObject(
                "SELECT onboarding_completed_at FROM profiles WHERE user_id = ?",
                OffsetDateTime.class,
                userId
        ).toInstant();
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

    private String requestJson(Object... values) {
        StringBuilder json = new StringBuilder("{\"legalActions\":[");
        for (int index = 0; index < values.length; index += 2) {
            if (index > 0) {
                json.append(',');
            }
            json.append("{\"documentId\":\"")
                    .append(values[index])
                    .append("\",\"actionType\":\"")
                    .append(values[index + 1])
                    .append("\"}");
        }
        return json.append("]}").toString();
    }
}
