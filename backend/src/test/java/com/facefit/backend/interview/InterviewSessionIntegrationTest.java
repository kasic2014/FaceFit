package com.facefit.backend.interview;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.TextNode;
import com.facefit.backend.document.application.CareerDocumentService;
import com.facefit.backend.document.storage.CareerDocumentStorage;
import com.facefit.backend.interview.api.InterviewSessionCreateRequest;
import com.facefit.backend.interview.api.InterviewSessionPatchRequest;
import com.facefit.backend.interview.application.InterviewSessionService;
import com.facefit.backend.jobposting.storage.JobPostingStorage;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.LinkedHashMap;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
class InterviewSessionIntegrationTest {

    private static final String URI = "/api/v1/interview-sessions";

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
        registry.add("facefit.job-postings.processing.async-enabled", () -> false);
        registry.add("facefit.job-postings.processing.recovery-enabled", () -> false);
        registry.add("facefit.job-postings.ocr.enabled", () -> false);
    }

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private InterviewSessionService interviewSessionService;

    @Autowired
    private CareerDocumentService careerDocumentService;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @MockitoBean
    private CareerDocumentStorage careerDocumentStorage;

    @MockitoBean
    private JobPostingStorage jobPostingStorage;

    @BeforeEach
    void clearDatabase() {
        jdbcTemplate.execute(
                "TRUNCATE TABLE interview_sessions, job_postings, career_documents, "
                        + "user_legal_records, legal_documents, profiles, auth.users CASCADE"
        );
        reset(careerDocumentStorage, jobPostingStorage);
    }

    @Test
    void everySessionEndpointRequiresAuthentication() throws Exception {
        UUID id = UUID.randomUUID();

        mockMvc.perform(post(URI)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(get(URI + "/" + id))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(patch(URI + "/" + id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"persona\":\"친절한 면접관\"}"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void inactiveAndIncompleteMembersCannotCreateSessions() throws Exception {
        UUID blocked = insertProfile("BLOCKED", "COMPLETED");
        UUID incomplete = insertProfile("ACTIVE", "NOT_STARTED");

        create(blocked, "{}")
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("MEMBER_ACCESS_DENIED"));
        create(incomplete, "{}")
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("ONBOARDING_REQUIRED"));
    }

    @Test
    void createsDraftWithOptionalCoverAndExactEightFieldSnapshot() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume = insertDocument(userId, "RESUME", "READY", null);
        UUID cover = insertDocument(userId, "COVER_LETTER", "READY", null);
        UUID posting = insertPosting(userId, "READY", null, "회사 A");

        UUID sessionId = createSession(userId, resume, cover, posting);

        mockMvc.perform(get(URI + "/" + sessionId).with(userJwt(userId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.resumeDocumentId").value(resume.toString()))
                .andExpect(jsonPath("$.data.coverLetterDocumentId").value(cover.toString()))
                .andExpect(jsonPath("$.data.jobPostingId").value(posting.toString()))
                .andExpect(jsonPath("$.data.persona").value("친절한 면접관"))
                .andExpect(jsonPath("$.data.difficulty").value("중간"))
                .andExpect(jsonPath("$.data.status").value("DRAFT"))
                .andExpect(jsonPath("$.data.companyName").value("회사 A"))
                .andExpect(jsonPath("$.data.targetRole").value("백엔드 개발자"))
                .andExpect(jsonPath("$.data.mainResponsibilities").value("API 개발"))
                .andExpect(jsonPath("$.data.qualifications").value("Java 경험"))
                .andExpect(jsonPath("$.data.preferredQualifications").value("Spring 경험"))
                .andExpect(jsonPath("$.data.technologiesTools").value("Java, PostgreSQL"))
                .andExpect(jsonPath("$.data.coreCompetencies").value("문제 해결"))
                .andExpect(jsonPath("$.data.companyBusinessIntro").value("채용 플랫폼"))
                .andExpect(jsonPath("$.data.currentQuestionOrder").isEmpty())
                .andExpect(jsonPath("$.data.createdAt").isNotEmpty())
                .andExpect(jsonPath("$.data.updatedAt").isNotEmpty());
    }

    @Test
    void createsWithoutCoverAndNormalizesLimitedSettings() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume = insertDocument(userId, "RESUME", "READY", null);
        UUID posting = insertPosting(userId, "READY", null, "회사 A");

        create(userId, createBody(resume, null, posting, "  차분한 면접관  ", "  쉬움  "))
                .andExpect(status().isOk());

        assertThat(jdbcTemplate.queryForObject(
                "SELECT persona FROM interview_sessions",
                String.class
        )).isEqualTo("차분한 면접관");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT difficulty FROM interview_sessions",
                String.class
        )).isEqualTo("쉬움");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT cover_letter_document_id IS NULL FROM interview_sessions",
                Boolean.class
        )).isTrue();
    }

    @Test
    void createRejectsMalformedUnknownAndClientControlledFields() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume = insertDocument(userId, "RESUME", "READY", null);
        UUID posting = insertPosting(userId, "READY", null, "회사 A");

        for (String extra : new String[]{
                "\"language\":\"en\"",
                "\"companyName\":\"위조\"",
                "\"status\":\"COMPLETED\""
        }) {
            String body = createBody(resume, null, posting, "면접관", "중간");
            create(userId, body.substring(0, body.length() - 1) + "," + extra + "}")
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
        }
        create(userId, """
                {
                  "resumeDocumentId": "not-a-uuid",
                  "jobPostingId": "%s",
                  "persona": "면접관",
                  "difficulty": "중간"
                }
                """.formatted(posting))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
        create(userId, createBody(resume, null, posting, " \n ", "중간"))
                .andExpect(status().isBadRequest());
        create(userId, createBody(resume, null, posting, "면접관", "보통\t난이도"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createRejectsForeignMissingDeletedWrongTypeAndNotReadyDocuments() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID posting = insertPosting(owner, "READY", null, "회사 A");
        UUID foreign = insertDocument(other, "RESUME", "READY", null);
        UUID deleted = insertDocument(owner, "RESUME", "READY", OffsetDateTime.now());
        UUID wrongType = insertDocument(owner, "COVER_LETTER", "READY", null);
        UUID processing = insertDocument(owner, "RESUME", "PROCESSING", null);
        UUID failed = insertDocument(owner, "RESUME", "FAILED", null);

        for (UUID hidden : Set.of(UUID.randomUUID(), foreign, deleted)) {
            create(owner, createBody(hidden, null, posting, "면접관", "중간"))
                    .andExpect(status().isNotFound())
                    .andExpect(jsonPath("$.error.code").value("RESOURCE_NOT_FOUND"));
        }
        create(owner, createBody(wrongType, null, posting, "면접관", "중간"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("INVALID_SESSION_RESOURCE"));
        for (UUID notReady : Set.of(processing, failed)) {
            create(owner, createBody(notReady, null, posting, "면접관", "중간"))
                    .andExpect(status().isConflict())
                    .andExpect(jsonPath("$.error.code").value("RESOURCE_NOT_READY"));
        }
    }

    @Test
    void createValidatesCoverTypeOwnershipReadinessAndDistinctness() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID resume = insertDocument(owner, "RESUME", "READY", null);
        UUID posting = insertPosting(owner, "READY", null, "회사 A");
        UUID foreignCover = insertDocument(other, "COVER_LETTER", "READY", null);
        UUID wrongCover = insertDocument(owner, "RESUME", "READY", null);
        UUID failedCover = insertDocument(owner, "COVER_LETTER", "FAILED", null);

        create(owner, createBody(resume, foreignCover, posting, "면접관", "중간"))
                .andExpect(status().isNotFound());
        create(owner, createBody(resume, wrongCover, posting, "면접관", "중간"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("INVALID_SESSION_RESOURCE"));
        create(owner, createBody(resume, failedCover, posting, "면접관", "중간"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("RESOURCE_NOT_READY"));
        create(owner, createBody(resume, resume, posting, "면접관", "중간"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void createRejectsForeignDeletedNotReadyAndIncompleteJobPostings() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID resume = insertDocument(owner, "RESUME", "READY", null);
        UUID foreign = insertPosting(other, "READY", null, "타사");
        UUID deleted = insertPosting(owner, "READY", OffsetDateTime.now(), "삭제 회사");
        UUID processing = insertPosting(owner, "PROCESSING", null, "처리 회사");
        UUID failed = insertPosting(owner, "FAILED", null, "실패 회사");
        UUID incomplete = insertPosting(owner, "READY", null, null);

        for (UUID hidden : Set.of(UUID.randomUUID(), foreign, deleted)) {
            create(owner, createBody(resume, null, hidden, "면접관", "중간"))
                    .andExpect(status().isNotFound());
        }
        for (UUID notReady : Set.of(processing, failed, incomplete)) {
            create(owner, createBody(resume, null, notReady, "면접관", "중간"))
                    .andExpect(status().isConflict())
                    .andExpect(jsonPath("$.error.code").value("RESOURCE_NOT_READY"));
        }
    }

    @Test
    void detailUsesImmutableSnapshotAndHidesInternalData() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume = insertDocument(userId, "RESUME", "READY", null);
        UUID posting = insertPosting(userId, "READY", null, "원래 회사");
        UUID sessionId = createSession(userId, resume, null, posting);

        jdbcTemplate.update(
                "UPDATE job_postings SET company_name = '변경 회사', raw_text = '비공개 원문', "
                        + "storage_bucket = NULL, storage_path = NULL WHERE job_posting_id = ?",
                posting
        );

        mockMvc.perform(get(URI + "/" + sessionId).with(userJwt(userId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.companyName").value("원래 회사"))
                .andExpect(jsonPath("$.data.userId").doesNotExist())
                .andExpect(jsonPath("$.data.rowVersion").doesNotExist())
                .andExpect(jsonPath("$.data.version").doesNotExist())
                .andExpect(jsonPath("$.data.storageBucket").doesNotExist())
                .andExpect(jsonPath("$.data.storagePath").doesNotExist())
                .andExpect(jsonPath("$.data.originalFileName").doesNotExist())
                .andExpect(jsonPath("$.data.rawText").doesNotExist())
                .andExpect(jsonPath("$.data.extractedText").doesNotExist())
                .andExpect(jsonPath("$.data.processingError").doesNotExist());
    }

    @Test
    void detailReturnsSameNotFoundForMissingAndOtherOwnersSession() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID resume = insertDocument(owner, "RESUME", "READY", null);
        UUID posting = insertPosting(owner, "READY", null, "회사 A");
        UUID sessionId = createSession(owner, resume, null, posting);

        for (UUID hidden : Set.of(UUID.randomUUID(), sessionId)) {
            UUID requester = hidden.equals(sessionId) ? other : owner;
            mockMvc.perform(get(URI + "/" + hidden).with(userJwt(requester)))
                    .andExpect(status().isNotFound())
                    .andExpect(jsonPath("$.error.code").value("RESOURCE_NOT_FOUND"));
        }
    }

    @Test
    void draftPatchChangesSettingsDocumentsAndExplicitlyClearsCover() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume1 = insertDocument(userId, "RESUME", "READY", null);
        UUID resume2 = insertDocument(userId, "RESUME", "READY", null);
        UUID cover = insertDocument(userId, "COVER_LETTER", "READY", null);
        UUID posting = insertPosting(userId, "READY", null, "회사 A");
        UUID sessionId = createSession(userId, resume1, null, posting);

        patchSession(userId, sessionId, """
                {
                  "resumeDocumentId": "%s",
                  "coverLetterDocumentId": "%s",
                  "persona": "  압박 면접관  ",
                  "difficulty": "어려움"
                }
                """.formatted(resume2, cover))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.resumeDocumentId").value(resume2.toString()))
                .andExpect(jsonPath("$.data.coverLetterDocumentId").value(cover.toString()))
                .andExpect(jsonPath("$.data.persona").value("압박 면접관"))
                .andExpect(jsonPath("$.data.difficulty").value("어려움"))
                .andExpect(jsonPath("$.data.companyName").value("회사 A"));

        patchSession(userId, sessionId, "{\"coverLetterDocumentId\":null}")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.coverLetterDocumentId").isEmpty());
    }

    @Test
    void changingJobAtomicallyReplacesAllEightSnapshotFields() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume = insertDocument(userId, "RESUME", "READY", null);
        UUID posting1 = insertPosting(userId, "READY", null, "회사 A");
        UUID posting2 = insertPosting(userId, "READY", null, "회사 B");
        jdbcTemplate.update(
                """
                UPDATE job_postings
                SET target_role = '데이터 엔지니어',
                    main_responsibilities = '파이프라인 개발',
                    qualifications = 'SQL 경험',
                    preferred_qualifications = 'Airflow 경험',
                    technologies_tools = 'Python, Airflow',
                    core_competencies = '데이터 모델링',
                    company_business_intro = '데이터 플랫폼'
                WHERE job_posting_id = ?
                """,
                posting2
        );
        UUID sessionId = createSession(userId, resume, null, posting1);

        patchSession(userId, sessionId, "{\"jobPostingId\":\"" + posting2 + "\"}")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.companyName").value("회사 B"))
                .andExpect(jsonPath("$.data.targetRole").value("데이터 엔지니어"))
                .andExpect(jsonPath("$.data.mainResponsibilities").value("파이프라인 개발"))
                .andExpect(jsonPath("$.data.qualifications").value("SQL 경험"))
                .andExpect(jsonPath("$.data.preferredQualifications").value("Airflow 경험"))
                .andExpect(jsonPath("$.data.technologiesTools").value("Python, Airflow"))
                .andExpect(jsonPath("$.data.coreCompetencies").value("데이터 모델링"))
                .andExpect(jsonPath("$.data.companyBusinessIntro").value("데이터 플랫폼"));

        jdbcTemplate.update(
                "UPDATE job_postings SET company_name = '또 변경' WHERE job_posting_id = ?",
                posting2
        );
        patchSession(userId, sessionId, "{\"persona\":\"새 면접관\"}")
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.companyName").value("회사 B"));
    }

    @Test
    void patchRejectsEmptyUnknownNullAndNonDraftRequests() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume = insertDocument(userId, "RESUME", "READY", null);
        UUID posting = insertPosting(userId, "READY", null, "회사 A");
        UUID sessionId = createSession(userId, resume, null, posting);

        for (String invalid : new String[]{
                "{}",
                "{\"language\":\"en\"}",
                "{\"resumeDocumentId\":null}",
                "{\"jobPostingId\":null}",
                "{\"persona\":null}",
                "{\"difficulty\":null}"
        }) {
            patchSession(userId, sessionId, invalid)
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
        }

        jdbcTemplate.update(
                "UPDATE interview_sessions SET session_status = 'IN_PROGRESS' WHERE session_id = ?",
                sessionId
        );
        patchSession(userId, sessionId, "{\"persona\":\"변경 시도\"}")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("INVALID_STATE"));
    }

    @Test
    void patchReturnsNotFoundForOtherOwnersSession() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID resume = insertDocument(owner, "RESUME", "READY", null);
        UUID posting = insertPosting(owner, "READY", null, "회사 A");
        UUID sessionId = createSession(owner, resume, null, posting);

        patchSession(other, sessionId, "{\"persona\":\"변경 시도\"}")
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("RESOURCE_NOT_FOUND"));
    }

    @Test
    void nonTerminalReferencesBlockDeletesAndTerminalReferencesAllowThem() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume = insertDocument(userId, "RESUME", "READY", null);
        UUID cover = insertDocument(userId, "COVER_LETTER", "READY", null);
        UUID posting = insertPosting(userId, "READY", null, "회사 A");
        UUID sessionId = createSession(userId, resume, cover, posting);

        for (UUID documentId : Set.of(resume, cover)) {
            mockMvc.perform(delete("/api/v1/career-documents/" + documentId)
                            .with(userJwt(userId)))
                    .andExpect(status().isConflict())
                    .andExpect(jsonPath("$.error.code").value("RESOURCE_IN_USE"));
        }
        mockMvc.perform(delete("/api/v1/job-postings/" + posting)
                        .with(userJwt(userId)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("RESOURCE_IN_USE"));

        jdbcTemplate.update(
                "UPDATE interview_sessions SET session_status = 'COMPLETED', completed_at = now() "
                        + "WHERE session_id = ?",
                sessionId
        );
        for (UUID documentId : Set.of(resume, cover)) {
            mockMvc.perform(delete("/api/v1/career-documents/" + documentId)
                            .with(userJwt(userId)))
                    .andExpect(status().isNoContent());
        }
        mockMvc.perform(delete("/api/v1/job-postings/" + posting)
                        .with(userJwt(userId)))
                .andExpect(status().isNoContent());
        verify(jobPostingStorage, never()).delete(anyString(), anyString());

        mockMvc.perform(get(URI + "/" + sessionId).with(userJwt(userId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.companyName").value("회사 A"));
    }

    @Test
    void concurrentCreateAndDocumentDeleteNeverLeavesSessionOnDeletedResource()
            throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume = insertDocument(userId, "RESUME", "READY", null);
        UUID posting = insertPosting(userId, "READY", null, "회사 A");
        Jwt token = jwtToken(userId);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> createResult = executor.submit(() -> {
                start.await();
                try {
                    interviewSessionService.create(
                            token,
                            new InterviewSessionCreateRequest(
                                    resume,
                                    null,
                                    posting,
                                    "면접관",
                                    "중간"
                            )
                    );
                    return "CREATED";
                } catch (RuntimeException exception) {
                    return exception.getClass().getSimpleName();
                }
            });
            Future<String> deleteResult = executor.submit(() -> {
                start.await();
                try {
                    careerDocumentService.delete(token, resume);
                    return "DELETED";
                } catch (RuntimeException exception) {
                    return exception.getClass().getSimpleName();
                }
            });

            start.countDown();
            Set<String> results = Set.of(
                    createResult.get(10, TimeUnit.SECONDS),
                    deleteResult.get(10, TimeUnit.SECONDS)
            );
            assertThat(
                    results.containsAll(Set.of("CREATED", "ResourceInUseException"))
                            || results.containsAll(Set.of(
                                    "DELETED",
                                    "ResourceNotFoundException"
                            ))
            ).isTrue();
            int sessions = jdbcTemplate.queryForObject(
                    "SELECT count(*) FROM interview_sessions",
                    Integer.class
            );
            boolean deleted = jdbcTemplate.queryForObject(
                    "SELECT deleted_at IS NOT NULL FROM career_documents WHERE document_id = ?",
                    Boolean.class,
                    resume
            );
            assertThat(sessions == 0 || !deleted).isTrue();
        } finally {
            executor.shutdownNow();
        }
    }

    @Test
    void concurrentPartialPatchesPreserveBothUpdates() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID resume = insertDocument(userId, "RESUME", "READY", null);
        UUID posting = insertPosting(userId, "READY", null, "회사 A");
        UUID sessionId = createSession(userId, resume, null, posting);
        Jwt token = jwtToken(userId);
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<?> persona = executor.submit(() -> {
                await(start);
                interviewSessionService.patch(
                        token,
                        sessionId,
                        new InterviewSessionPatchRequest(Map.of(
                                "persona",
                                TextNode.valueOf("새 면접관")
                        ))
                );
            });
            Future<?> difficulty = executor.submit(() -> {
                await(start);
                interviewSessionService.patch(
                        token,
                        sessionId,
                        new InterviewSessionPatchRequest(Map.of(
                                "difficulty",
                                TextNode.valueOf("어려움")
                        ))
                );
            });

            start.countDown();
            persona.get(10, TimeUnit.SECONDS);
            difficulty.get(10, TimeUnit.SECONDS);
            assertThat(jdbcTemplate.queryForMap(
                    "SELECT persona, difficulty FROM interview_sessions WHERE session_id = ?",
                    sessionId
            )).containsEntry("persona", "새 면접관")
                    .containsEntry("difficulty", "어려움");
        } finally {
            executor.shutdownNow();
        }
    }

    private ResultActions create(UUID userId, String body) throws Exception {
        return mockMvc.perform(post(URI)
                .with(userJwt(userId))
                .contentType(MediaType.APPLICATION_JSON)
                .content(body));
    }

    private ResultActions patchSession(UUID userId, UUID sessionId, String body)
            throws Exception {
        return mockMvc.perform(patch(URI + "/" + sessionId)
                .with(userJwt(userId))
                .contentType(MediaType.APPLICATION_JSON)
                .content(body));
    }

    private UUID createSession(
            UUID userId,
            UUID resume,
            UUID cover,
            UUID posting
    ) throws Exception {
        String response = create(
                userId,
                createBody(resume, cover, posting, "친절한 면접관", "중간")
        )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("DRAFT"))
                .andReturn()
                .getResponse()
                .getContentAsString();
        return UUID.fromString(
                objectMapper.readTree(response).path("data").path("sessionId").asText()
        );
    }

    private String createBody(
            UUID resume,
            UUID cover,
            UUID posting,
            String persona,
            String difficulty
    ) throws Exception {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("resumeDocumentId", resume.toString());
        body.put("coverLetterDocumentId", cover == null ? null : cover.toString());
        body.put("jobPostingId", posting.toString());
        body.put("persona", persona);
        body.put("difficulty", difficulty);
        return objectMapper.writeValueAsString(body);
    }

    private UUID insertCompletedProfile() {
        return insertProfile("ACTIVE", "COMPLETED");
    }

    private UUID insertProfile(String memberStatus, String onboardingStatus) {
        UUID userId = UUID.randomUUID();
        jdbcTemplate.update("INSERT INTO auth.users (id) VALUES (?)", userId);
        jdbcTemplate.update(
                """
                INSERT INTO profiles (
                    user_id, member_status, onboarding_status, onboarding_completed_at
                ) VALUES (?, ?, ?, ?)
                """,
                userId,
                memberStatus,
                onboardingStatus,
                "COMPLETED".equals(onboardingStatus) ? OffsetDateTime.now() : null
        );
        return userId;
    }

    private UUID insertDocument(
            UUID userId,
            String type,
            String status,
            OffsetDateTime deletedAt
    ) {
        UUID id = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO career_documents (
                    document_id, user_id, document_type, original_file_name,
                    storage_bucket, storage_path, mime_type, file_size_bytes,
                    processing_status, deleted_at
                ) VALUES (?, ?, ?, ?, 'career-documents', ?, 'application/pdf', 100, ?, ?)
                """,
                id,
                userId,
                type,
                id + ".pdf",
                userId + "/" + id + ".pdf",
                status,
                deletedAt
        );
        return id;
    }

    private UUID insertPosting(
            UUID userId,
            String status,
            OffsetDateTime deletedAt,
            String companyName
    ) {
        UUID id = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO job_postings (
                    job_posting_id, user_id, input_type, raw_text,
                    company_name, target_role, main_responsibilities, qualifications,
                    preferred_qualifications, technologies_tools, core_competencies,
                    company_business_intro, processing_status, deleted_at
                ) VALUES (
                    ?, ?, 'TEXT', '공고 원문',
                    ?, '백엔드 개발자', 'API 개발', 'Java 경험',
                    'Spring 경험', 'Java, PostgreSQL', '문제 해결',
                    '채용 플랫폼', ?, ?
                )
                """,
                id,
                userId,
                companyName,
                status,
                deletedAt
        );
        return id;
    }

    private org.springframework.security.test.web.servlet.request
            .SecurityMockMvcRequestPostProcessors.JwtRequestPostProcessor userJwt(UUID userId) {
        return jwt().jwt(token -> token
                .subject(userId.toString())
                .claim("role", "authenticated"));
    }

    private Jwt jwtToken(UUID userId) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("verified-token")
                .header("alg", "none")
                .subject(userId.toString())
                .claim("role", "authenticated")
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .build();
    }

    private void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(exception);
        }
    }
}
