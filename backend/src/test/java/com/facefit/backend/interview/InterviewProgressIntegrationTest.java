package com.facefit.backend.interview;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.facefit.backend.common.exception.InterviewProgressException;
import com.facefit.backend.common.exception.StorageOperationException;
import com.facefit.backend.document.storage.CareerDocumentStorage;
import com.facefit.backend.interview.api.InterviewCompletionRequest;
import com.facefit.backend.interview.application.AnswerAnalysisWorker;
import com.facefit.backend.interview.application.InterviewAnswerService;
import com.facefit.backend.interview.application.InterviewProgressService;
import com.facefit.backend.interview.application.QuestionGenerationWorker;
import com.facefit.backend.interview.domain.AnswerEndedBy;
import com.facefit.backend.interview.domain.InterviewCompletionType;
import com.facefit.backend.interview.domain.InterviewQuestionType;
import com.facefit.backend.interview.integration.AnalysisResult;
import com.facefit.backend.interview.integration.ContentAnalysisPort;
import com.facefit.backend.interview.integration.CvAnalysisPort;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.integration.QuestionGenerationPort;
import com.facefit.backend.interview.integration.QuestionGenerationRequest;
import com.facefit.backend.interview.integration.QuestionGenerationResponse;
import com.facefit.backend.interview.integration.SttPort;
import com.facefit.backend.interview.integration.SttResult;
import com.facefit.backend.interview.integration.VoiceAnalysisPort;
import com.facefit.backend.interview.storage.InterviewAnswerStorage;
import com.facefit.backend.jobposting.storage.JobPostingStorage;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
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
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
class InterviewProgressIntegrationTest {

    private static final String SESSION_URI = "/api/v1/interview-sessions";

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
        registry.add("facefit.interview.processing.dispatch-enabled", () -> false);
        registry.add("facefit.interview.processing.recovery-enabled", () -> false);
    }

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private InterviewProgressService progressService;

    @Autowired
    private InterviewAnswerService answerService;

    @Autowired
    private QuestionGenerationWorker questionWorker;

    @Autowired
    private AnswerAnalysisWorker answerWorker;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @MockitoBean
    private CareerDocumentStorage careerDocumentStorage;

    @MockitoBean
    private JobPostingStorage jobPostingStorage;

    @MockitoBean
    private InterviewAnswerStorage answerStorage;

    @MockitoBean
    private QuestionGenerationPort questionPort;

    @MockitoBean
    private SttPort sttPort;

    @MockitoBean
    private CvAnalysisPort cvPort;

    @MockitoBean
    private VoiceAnalysisPort voicePort;

    @MockitoBean
    private ContentAnalysisPort contentPort;

    @BeforeEach
    void clearDatabase() {
        jdbcTemplate.execute(
                "TRUNCATE TABLE interview_sessions, job_postings, career_documents, "
                        + "user_legal_records, legal_documents, profiles, auth.users "
                        + "CASCADE"
        );
        reset(
                careerDocumentStorage,
                jobPostingStorage,
                answerStorage,
                questionPort,
                sttPort,
                cvPort,
                voicePort,
                contentPort
        );
        when(answerStorage.canonicalUrl(any(), anyString(), anyString()))
                .thenReturn(java.net.URI.create(
                        "https://kr.object.ncloudstorage.com/facefit-interview-videos/test.mp4"
                ));
    }

    @Test
    void startRequiresAuthenticationOwnershipOnboardingAndValidIdempotencyKey()
            throws Exception {
        Fixture fixture = insertFixture("ACTIVE", "COMPLETED");

        mockMvc.perform(post(startUri(fixture.sessionId())))
                .andExpect(status().isUnauthorized());
        start(fixture.userId(), fixture.sessionId(), null)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_KEY_REQUIRED"));
        start(fixture.userId(), fixture.sessionId(), "bad key")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code")
                        .value("INVALID_IDEMPOTENCY_KEY"));

        UUID other = insertProfile("ACTIVE", "COMPLETED");
        start(other, fixture.sessionId(), "other-user-key")
                .andExpect(status().isNotFound());

        Fixture pending = insertFixture("ACTIVE", "NOT_STARTED");
        start(pending.userId(), pending.sessionId(), "pending-user-key")
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("ONBOARDING_REQUIRED"));
    }

    @Test
    void startQueuesOnceKeepsDraftAndReplaysSameResponse() throws Exception {
        Fixture fixture = insertFixture("ACTIVE", "COMPLETED");

        String first = start(
                fixture.userId(),
                fixture.sessionId(),
                "start-key-0001"
        )
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.sessionStatus").value("DRAFT"))
                .andExpect(jsonPath("$.data.questionGenerationStatus").value("QUEUED"))
                .andExpect(jsonPath("$.data.currentQuestion").isEmpty())
                .andReturn().getResponse().getContentAsString();
        String replay = start(
                fixture.userId(),
                fixture.sessionId(),
                "start-key-0001"
        )
                .andExpect(status().isAccepted())
                .andReturn().getResponse().getContentAsString();

        assertThat(objectMapper.readTree(replay).path("data"))
                .isEqualTo(objectMapper.readTree(first).path("data"));
        assertThat(count("interview_processing_jobs")).isEqualTo(1);
        assertThat(count("api_idempotency_records")).isEqualTo(1);
        assertThat(jdbcTemplate.queryForMap(
                "SELECT session_status, started_at FROM interview_sessions "
                        + "WHERE session_id = ?",
                fixture.sessionId()
        )).containsEntry("session_status", "DRAFT")
                .containsEntry("started_at", null);

        start(fixture.userId(), fixture.sessionId(), "start-key-0002")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_REQUEST_IN_PROGRESS"));

        mockMvc.perform(get(
                        SESSION_URI + "/" + fixture.sessionId() + "/questions/current"
                ).with(userJwt(fixture.userId())))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.progressStatus")
                        .value("QUESTION_GENERATION_IN_PROGRESS"))
                .andExpect(jsonPath("$.data.canAnswer").value(false));
    }

    @Test
    void questionWorkerAtomicallyStoresTenQuestionsAndStartsSession()
            throws Exception {
        Fixture fixture = insertFixture("ACTIVE", "COMPLETED");
        UUID jobId = queueStart(fixture, "question-success-key");
        stubValidQuestions();

        questionWorker.process(jobId);
        questionWorker.process(jobId);

        assertThat(count("interview_turns")).isEqualTo(10);
        assertThat(jdbcTemplate.queryForMap(
                "SELECT session_status, current_question_order, "
                        + "started_at IS NOT NULL AS started "
                        + "FROM interview_sessions WHERE session_id = ?",
                fixture.sessionId()
        )).containsEntry("session_status", "IN_PROGRESS")
                .containsEntry("current_question_order", 1)
                .containsEntry("started", true);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT job_status FROM interview_processing_jobs WHERE job_id = ?",
                String.class,
                jobId
        )).isEqualTo("SUCCEEDED");
        verify(questionPort, times(1)).generate(any());

        mockMvc.perform(get(
                        SESSION_URI + "/" + fixture.sessionId() + "/questions/current"
                ).with(userJwt(fixture.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.currentQuestion.order").value(1))
                .andExpect(jsonPath("$.data.currentQuestion.type")
                        .value("INTRODUCTION"))
                .andExpect(jsonPath("$.data.canAnswer").value(true))
                .andExpect(jsonPath("$.data.canFinish").value(false));
    }

    @Test
    void invalidQuestionResponsesRetryThenFailWithoutPartialRows()
            throws Exception {
        Fixture fixture = insertFixture("ACTIVE", "COMPLETED");
        UUID jobId = queueStart(fixture, "question-failure-key");
        when(questionPort.generate(any())).thenAnswer(invocation -> {
            QuestionGenerationRequest request = invocation.getArgument(0);
            return PortResult.success(new QuestionGenerationResponse(
                    "1.0",
                    request.generationRequestId(),
                    validQuestions().subList(0, 9)
            ));
        });

        for (int attempt = 1; attempt <= 3; attempt++) {
            questionWorker.process(jobId);
            if (attempt < 3) {
                assertThat(jobStatus(jobId)).isEqualTo("QUEUED");
                jdbcTemplate.update(
                        "UPDATE interview_processing_jobs "
                                + "SET next_retry_at = now() - interval '1 second' "
                                + "WHERE job_id = ?",
                        jobId
                );
            }
        }

        assertThat(jobStatus(jobId)).isEqualTo("FAILED");
        assertThat(count("interview_turns")).isZero();
        assertThat(jdbcTemplate.queryForMap(
                "SELECT session_status, started_at FROM interview_sessions "
                        + "WHERE session_id = ?",
                fixture.sessionId()
        )).containsEntry("session_status", "DRAFT")
                .containsEntry("started_at", null);

        mockMvc.perform(get(
                        SESSION_URI + "/" + fixture.sessionId() + "/questions/current"
                ).with(userJwt(fixture.userId())))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error.code")
                        .value("QUESTION_GENERATION_FAILED"))
                .andExpect(jsonPath("$.error.retryable").value(true));

        start(fixture.userId(), fixture.sessionId(), "question-retry-new-key")
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.questionGenerationStatus").value("QUEUED"));
        assertThat(count("interview_processing_jobs")).isEqualTo(2);
    }

    @Test
    void answerUploadIsPrivateAtomicAndIdempotent() throws Exception {
        Fixture fixture = startedFixture();
        UUID questionId = turnId(fixture.sessionId(), 1);
        byte[] media = TestMediaFiles.mp4(true, true, 60);

        String first = submitAnswer(
                fixture.userId(),
                fixture.sessionId(),
                questionId,
                "answer-key-0001",
                media
        )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.answerStatus").value("QUEUED"))
                .andExpect(jsonPath("$.data.nextQuestionStatus").value("READY"))
                .andExpect(jsonPath("$.data.storageBucket").doesNotExist())
                .andExpect(jsonPath("$.data.storagePath").doesNotExist())
                .andReturn().getResponse().getContentAsString();
        String replay = submitAnswer(
                fixture.userId(),
                fixture.sessionId(),
                questionId,
                "answer-key-0001",
                media
        )
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        assertThat(objectMapper.readTree(replay).path("data"))
                .isEqualTo(objectMapper.readTree(first).path("data"));
        assertThat(count("interview_answers")).isEqualTo(1);
        assertThat(count("interview_processing_jobs")).isEqualTo(5);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT storage_bucket FROM interview_answers",
                String.class
        )).isEqualTo("facefit-interview-videos");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT storage_path FROM interview_answers",
                String.class
        )).matches(
                "sessions/" + fixture.sessionId()
                        + "/turns/" + questionId
                        + "/[0-9a-f-]+\\.mp4"
        );
        assertThat(jdbcTemplate.queryForObject(
                "SELECT storage_provider FROM interview_answers",
                String.class
        )).isEqualTo("NCLOUD");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT storage_url FROM interview_answers",
                String.class
        )).isEqualTo(
                "https://kr.object.ncloudstorage.com/facefit-interview-videos/test.mp4"
        ).doesNotContain("?");
        verify(answerStorage, times(1))
                .upload(any(), anyString(), anyString(), anyString(),
                        anyLong(), anyString(), any());

        submitAnswer(
                fixture.userId(),
                fixture.sessionId(),
                turnId(fixture.sessionId(), 2),
                "answer-key-0001",
                media
        )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("IDEMPOTENCY_KEY_REUSED"));
        submitAnswer(
                fixture.userId(),
                fixture.sessionId(),
                questionId,
                "answer-key-0002",
                media
        )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("ANSWER_ALREADY_SUBMITTED"));

        mockMvc.perform(get(
                        SESSION_URI + "/" + fixture.sessionId() + "/questions/current"
                ).with(userJwt(fixture.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.currentQuestion.order").value(2));
    }

    @Test
    void invalidAnswerMediaDoesNotUploadOrCreateRows() throws Exception {
        Fixture fixture = startedFixture();
        UUID questionId = turnId(fixture.sessionId(), 1);

        submitAnswer(
                fixture.userId(),
                fixture.sessionId(),
                questionId,
                "invalid-media-key",
                TestMediaFiles.mp4(true, false, 30)
        )
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_ANSWER_MEDIA"));

        verify(answerStorage, never())
                .upload(any(), anyString(), anyString(), anyString(),
                        anyLong(), anyString(), any());
        assertThat(count("interview_answers")).isZero();
    }

    @Test
    void storageFailureCompensatesReservationAndAllowsSafeRetry() throws Exception {
        Fixture fixture = startedFixture();
        UUID questionId = turnId(fixture.sessionId(), 1);
        byte[] media = TestMediaFiles.mp4(true, true, 30);
        doThrow(new StorageOperationException("TEST_UPLOAD_FAILED"))
                .when(answerStorage)
                .upload(any(), anyString(), anyString(), anyString(),
                        anyLong(), anyString(), any());

        submitAnswer(
                fixture.userId(),
                fixture.sessionId(),
                questionId,
                "storage-retry-key",
                media
        )
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error.code")
                        .value("STORAGE_OPERATION_FAILED"));

        assertThat(count("interview_answers")).isZero();
        assertThat(count("api_idempotency_records")).isEqualTo(1);
        verify(answerStorage, times(1))
                .delete(any(), anyString(), anyString());

        reset(answerStorage);
        when(answerStorage.canonicalUrl(any(), anyString(), anyString()))
                .thenReturn(java.net.URI.create(
                        "https://kr.object.ncloudstorage.com/facefit-interview-videos/test.mp4"
                ));
        submitAnswer(
                fixture.userId(),
                fixture.sessionId(),
                questionId,
                "storage-retry-key",
                media
        ).andExpect(status().isOk());
        assertThat(count("interview_answers")).isEqualTo(1);
    }

    @Test
    void answerStatusHidesStorageAndWorkersCompleteAllFourSteps() throws Exception {
        Fixture fixture = startedFixture();
        UUID questionId = turnId(fixture.sessionId(), 1);
        String response = submitAnswer(
                fixture.userId(),
                fixture.sessionId(),
                questionId,
                "analysis-key-001",
                TestMediaFiles.mp4(true, true, 30)
        )
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        UUID answerId = UUID.fromString(
                objectMapper.readTree(response).path("data").path("answerId").asText()
        );

        when(sttPort.transcribe(any()))
                .thenReturn(PortResult.success(new SttResult("테스트 전사문")));
        var cvPayload = objectMapper.createObjectNode();
        cvPayload.put("schemaVersion", "1.0");
        cvPayload.put("gazeScore", 80);
        cvPayload.put("postureScore", 81);
        cvPayload.putArray("feedback").add("시선 피드백");
        when(cvPort.analyze(any()))
                .thenReturn(PortResult.success(new AnalysisResult(cvPayload)));
        var voicePayload = objectMapper.createObjectNode();
        voicePayload.put("schemaVersion", "1.0");
        voicePayload.put("speechScore", 82);
        voicePayload.putArray("feedback").add("말하기 피드백");
        when(voicePort.analyze(any()))
                .thenReturn(PortResult.success(new AnalysisResult(voicePayload)));
        var contentPayload = objectMapper.createObjectNode();
        contentPayload.put("schemaVersion", "1.0");
        contentPayload.put("contentScore", 83);
        contentPayload.putArray("feedback").add("내용 피드백");
        when(contentPort.analyze(any()))
                .thenReturn(PortResult.success(new AnalysisResult(contentPayload)));

        for (UUID jobId : answerJobIds(answerId)) {
            answerWorker.process(jobId);
            answerWorker.process(jobId);
        }

        mockMvc.perform(get("/api/v1/interview-answers/" + answerId)
                        .with(userJwt(fixture.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.status").value("COMPLETED"))
                .andExpect(jsonPath("$.data.transcript").doesNotExist())
                .andExpect(jsonPath("$.data.processingSteps.length()").value(4))
                .andExpect(jsonPath("$.data.storageBucket").doesNotExist())
                .andExpect(jsonPath("$.data.storagePath").doesNotExist());

        UUID other = insertProfile("ACTIVE", "COMPLETED");
        mockMvc.perform(get("/api/v1/interview-answers/" + answerId)
                        .with(userJwt(other)))
                .andExpect(status().isNotFound());
    }

    @Test
    void normalCompletionRequiresTenAnswersButDoesNotWaitForAnalysis()
            throws Exception {
        Fixture fixture = startedFixture();
        for (int order = 1; order <= 10; order++) {
            submitAnswer(
                    fixture.userId(),
                    fixture.sessionId(),
                    turnId(fixture.sessionId(), order),
                    "normal-answer-" + order,
                    TestMediaFiles.mp4(true, true, 20)
            ).andExpect(status().isOk());
        }
        assertThat(jdbcTemplate.queryForObject(
                "SELECT count(*) FROM interview_processing_jobs "
                        + "WHERE job_type <> 'QUESTION_GENERATION' "
                        + "AND job_status = 'QUEUED'",
                Integer.class
        )).isEqualTo(40);

        mockMvc.perform(get(
                        SESSION_URI + "/" + fixture.sessionId() + "/questions/current"
                ).with(userJwt(fixture.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.progressStatus")
                        .value("ALL_QUESTIONS_ANSWERED"))
                .andExpect(jsonPath("$.data.currentQuestion").isEmpty())
                .andExpect(jsonPath("$.data.canFinish").value(true));

        String first = complete(
                fixture.userId(),
                fixture.sessionId(),
                "normal-completion-key",
                "NORMAL"
        )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.sessionStatus")
                        .value("INTERVIEW_COMPLETED"))
                .andExpect(jsonPath("$.data.completionType").value("NORMAL"))
                .andReturn().getResponse().getContentAsString();
        String replay = complete(
                fixture.userId(),
                fixture.sessionId(),
                "normal-completion-key",
                "NORMAL"
        )
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        assertThat(objectMapper.readTree(replay).path("data"))
                .isEqualTo(objectMapper.readTree(first).path("data"));
        assertThat(jdbcTemplate.queryForMap(
                "SELECT session_status, interview_completed_at IS NOT NULL AS ended, "
                        + "analysis_started_at FROM interview_sessions WHERE session_id = ?",
                fixture.sessionId()
        )).containsEntry("session_status", "INTERVIEW_COMPLETED")
                .containsEntry("ended", true)
                .containsEntry("analysis_started_at", null);
    }

    @Test
    void incompleteNormalCompletionFailsAndUserCanInterruptIdempotently()
            throws Exception {
        Fixture fixture = startedFixture();

        complete(
                fixture.userId(),
                fixture.sessionId(),
                "incomplete-normal-key",
                "NORMAL"
        )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("INCOMPLETE_INTERVIEW"));

        complete(
                fixture.userId(),
                fixture.sessionId(),
                "interrupt-key-0001",
                "USER_INTERRUPTED"
        )
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.sessionStatus").value("INTERRUPTED"));
        complete(
                fixture.userId(),
                fixture.sessionId(),
                "interrupt-key-0001",
                "USER_INTERRUPTED"
        ).andExpect(status().isOk());
        complete(
                fixture.userId(),
                fixture.sessionId(),
                "different-ending-key",
                "NORMAL"
        )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("INVALID_STATE"));

        assertThat(jdbcTemplate.queryForMap(
                "SELECT completion_type, interrupted_at IS NOT NULL AS ended "
                        + "FROM interview_sessions WHERE session_id = ?",
                fixture.sessionId()
        )).containsEntry("completion_type", "USER_INTERRUPTED")
                .containsEntry("ended", true);
    }

    @Test
    void draftQuestionGenerationCannotBeCompletedOrPatched() throws Exception {
        Fixture fixture = insertFixture("ACTIVE", "COMPLETED");
        queueStart(fixture, "draft-generation-key");

        complete(
                fixture.userId(),
                fixture.sessionId(),
                "draft-completion-key",
                "USER_INTERRUPTED"
        )
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("INVALID_STATE"));
        mockMvc.perform(org.springframework.test.web.servlet.request
                        .MockMvcRequestBuilders.patch(
                                SESSION_URI + "/" + fixture.sessionId()
                        )
                        .with(userJwt(fixture.userId()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"persona\":\"변경 시도\"}"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("INVALID_STATE"));
    }

    @Test
    void concurrentStartAndAnswerRequestsDoNotDuplicateWork() throws Exception {
        Fixture fixture = insertFixture("ACTIVE", "COMPLETED");
        Jwt token = jwtToken(fixture.userId());
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            List<Future<Integer>> starts = new ArrayList<>();
            for (int index = 0; index < 2; index++) {
                starts.add(executor.submit(() -> {
                    start.await();
                    return progressService.start(
                            token,
                            fixture.sessionId(),
                            "concurrent-start-key"
                    ).httpStatus();
                }));
            }
            start.countDown();
            assertThat(starts.get(0).get(10, TimeUnit.SECONDS)).isEqualTo(202);
            assertThat(starts.get(1).get(10, TimeUnit.SECONDS)).isEqualTo(202);
            assertThat(count("interview_processing_jobs")).isEqualTo(1);
        } finally {
            executor.shutdownNow();
        }

        UUID generationJob = latestGenerationJob(fixture.sessionId());
        stubValidQuestions();
        questionWorker.process(generationJob);
        UUID turnId = turnId(fixture.sessionId(), 1);
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "answer.bin",
                "video/mp4",
                TestMediaFiles.mp4(true, true, 20)
        );
        CountDownLatch answerStart = new CountDownLatch(1);
        ExecutorService answerExecutor = Executors.newFixedThreadPool(2);
        try {
            List<Future<String>> answers = new ArrayList<>();
            for (int index = 0; index < 2; index++) {
                String key = "concurrent-answer-" + index;
                answers.add(answerExecutor.submit(() -> {
                    answerStart.await();
                    try {
                        answerService.submit(
                                token,
                                fixture.sessionId(),
                                key,
                                turnId,
                                file,
                                20,
                                AnswerEndedBy.USER_BUTTON
                        );
                        return "OK";
                    } catch (InterviewProgressException exception) {
                        return exception.getErrorCode();
                    }
                }));
            }
            answerStart.countDown();
            assertThat(List.of(
                    answers.get(0).get(10, TimeUnit.SECONDS),
                    answers.get(1).get(10, TimeUnit.SECONDS)
            )).satisfiesExactlyInAnyOrder(
                    value -> assertThat(value).isEqualTo("OK"),
                    value -> assertThat(value).isIn(
                            "ANSWER_ALREADY_SUBMITTED",
                            "IDEMPOTENCY_REQUEST_IN_PROGRESS"
                    )
            );
            assertThat(count("interview_answers")).isEqualTo(1);
            assertThat(jdbcTemplate.queryForObject(
                    "SELECT count(*) FROM interview_processing_jobs "
                            + "WHERE job_type <> 'QUESTION_GENERATION'",
                    Integer.class
            )).isEqualTo(4);
        } finally {
            answerExecutor.shutdownNow();
        }
    }

    private Fixture startedFixture() throws Exception {
        Fixture fixture = insertFixture("ACTIVE", "COMPLETED");
        UUID jobId = queueStart(fixture, "fixture-start-" + UUID.randomUUID());
        stubValidQuestions();
        questionWorker.process(jobId);
        return fixture;
    }

    private UUID queueStart(Fixture fixture, String key) throws Exception {
        start(fixture.userId(), fixture.sessionId(), key)
                .andExpect(status().isAccepted());
        return latestGenerationJob(fixture.sessionId());
    }

    private UUID latestGenerationJob(UUID sessionId) {
        return jdbcTemplate.queryForObject(
                "SELECT job_id FROM interview_processing_jobs "
                        + "WHERE session_id = ? AND job_type = 'QUESTION_GENERATION' "
                        + "ORDER BY created_at DESC LIMIT 1",
                UUID.class,
                sessionId
        );
    }

    private void stubValidQuestions() {
        when(questionPort.generate(any())).thenAnswer(invocation -> {
            QuestionGenerationRequest request = invocation.getArgument(0);
            return PortResult.success(new QuestionGenerationResponse(
                    "1.0",
                    request.generationRequestId(),
                    validQuestions()
            ));
        });
    }

    private List<QuestionGenerationResponse.GeneratedQuestion> validQuestions() {
        List<QuestionGenerationResponse.GeneratedQuestion> questions =
                new ArrayList<>();
        questions.add(question(1, InterviewQuestionType.INTRODUCTION, "지원동기"));
        for (int order = 2; order <= 4; order++) {
            questions.add(question(order, InterviewQuestionType.EXPERIENCE, "경험"));
        }
        for (int order = 5; order <= 7; order++) {
            questions.add(question(order, InterviewQuestionType.JOB_ROLE, "직무"));
        }
        for (int order = 8; order <= 9; order++) {
            questions.add(question(order, InterviewQuestionType.BEHAVIORAL, "협업"));
        }
        questions.add(question(10, InterviewQuestionType.CLOSING, "성장계획"));
        return List.copyOf(questions);
    }

    private QuestionGenerationResponse.GeneratedQuestion question(
            int order,
            InterviewQuestionType type,
            String category
    ) {
        return new QuestionGenerationResponse.GeneratedQuestion(
                order,
                type,
                category,
                order + "번째 면접 질문입니다."
        );
    }

    private ResultActions start(UUID userId, UUID sessionId, String key)
            throws Exception {
        var builder = post(startUri(sessionId)).with(userJwt(userId));
        if (key != null) {
            builder.header("Idempotency-Key", key);
        }
        return mockMvc.perform(builder);
    }

    private String startUri(UUID sessionId) {
        return SESSION_URI + "/" + sessionId + "/start";
    }

    private ResultActions submitAnswer(
            UUID userId,
            UUID sessionId,
            UUID questionId,
            String key,
            byte[] media
    ) throws Exception {
        MockMultipartFile file = new MockMultipartFile(
                "file",
                "ignored-local-name.bin",
                "video/mp4",
                media
        );
        return mockMvc.perform(multipart(
                        SESSION_URI + "/" + sessionId + "/answers"
                )
                .file(file)
                .param("questionId", questionId.toString())
                .param("recordedDurationSec", "60")
                .param("endedBy", "USER_BUTTON")
                .header("Idempotency-Key", key)
                .with(userJwt(userId)));
    }

    private ResultActions complete(
            UUID userId,
            UUID sessionId,
            String key,
            String completionType
    ) throws Exception {
        return mockMvc.perform(post(
                        SESSION_URI + "/" + sessionId + "/completion"
                )
                .with(userJwt(userId))
                .header("Idempotency-Key", key)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"completionType\":\"" + completionType + "\"}"));
    }

    private Fixture insertFixture(String memberStatus, String onboardingStatus) {
        UUID userId = insertProfile(memberStatus, onboardingStatus);
        UUID resumeId = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO career_documents (
                    document_id, user_id, document_type, original_file_name,
                    storage_bucket, storage_path, mime_type, file_size_bytes,
                    processing_status, extracted_text
                ) VALUES (
                    ?, ?, 'RESUME', 'resume.pdf', 'career-documents', ?,
                    'application/pdf', 100, 'READY', '이력서 추출문'
                )
                """,
                resumeId,
                userId,
                userId + "/" + resumeId + ".pdf"
        );
        UUID postingId = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO job_postings (
                    job_posting_id, user_id, input_type, raw_text,
                    company_name, target_role, main_responsibilities,
                    qualifications, preferred_qualifications,
                    technologies_tools, core_competencies,
                    company_business_intro, processing_status
                ) VALUES (
                    ?, ?, 'TEXT', '공고 원문', '테스트 회사', '백엔드 개발자',
                    'API 개발', 'Java 경험', 'Spring 경험',
                    'Java, PostgreSQL', '문제 해결', '채용 플랫폼', 'READY'
                )
                """,
                postingId,
                userId
        );
        UUID sessionId = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO interview_sessions (
                    session_id, user_id, resume_document_id, job_posting_id,
                    persona, difficulty, session_status, voice_analysis_enabled,
                    snapshot_company_name, snapshot_target_role,
                    snapshot_main_responsibilities, snapshot_qualifications,
                    snapshot_preferred_qualifications,
                    snapshot_technologies_tools, snapshot_core_competencies,
                    snapshot_company_business_intro
                ) VALUES (
                    ?, ?, ?, ?, 'TECHNICAL_MANAGER', 'NORMAL', 'DRAFT', true,
                    '테스트 회사', '백엔드 개발자', 'API 개발', 'Java 경험',
                    'Spring 경험', 'Java, PostgreSQL', '문제 해결', '채용 플랫폼'
                )
                """,
                sessionId,
                userId,
                resumeId,
                postingId
        );
        return new Fixture(userId, sessionId);
    }

    private UUID insertProfile(String memberStatus, String onboardingStatus) {
        UUID userId = UUID.randomUUID();
        jdbcTemplate.update("INSERT INTO auth.users (id) VALUES (?)", userId);
        jdbcTemplate.update(
                """
                INSERT INTO profiles (
                    user_id, member_status, onboarding_status,
                    onboarding_completed_at, voice_analysis_consent,
                    voice_analysis_consented_at
                ) VALUES (?, ?, ?, ?, true, now())
                """,
                userId,
                memberStatus,
                onboardingStatus,
                "COMPLETED".equals(onboardingStatus)
                        ? OffsetDateTime.now()
                        : null
        );
        return userId;
    }

    private UUID turnId(UUID sessionId, int order) {
        return jdbcTemplate.queryForObject(
                "SELECT turn_id FROM interview_turns "
                        + "WHERE session_id = ? AND question_order = ?",
                UUID.class,
                sessionId,
                order
        );
    }

    private List<UUID> answerJobIds(UUID answerId) {
        return jdbcTemplate.queryForList(
                """
                SELECT job_id
                FROM interview_processing_jobs
                WHERE answer_id = ?
                ORDER BY CASE job_type
                    WHEN 'STT' THEN 1
                    WHEN 'CV' THEN 2
                    WHEN 'VOICE' THEN 3
                    WHEN 'CONTENT' THEN 4
                END
                """,
                UUID.class,
                answerId
        );
    }

    private int count(String table) {
        if (!List.of(
                "interview_processing_jobs",
                "api_idempotency_records",
                "interview_turns",
                "interview_answers"
        ).contains(table)) {
            throw new IllegalArgumentException("허용되지 않은 테스트 테이블입니다.");
        }
        return jdbcTemplate.queryForObject(
                "SELECT count(*) FROM " + table,
                Integer.class
        );
    }

    private String jobStatus(UUID jobId) {
        return jdbcTemplate.queryForObject(
                "SELECT job_status FROM interview_processing_jobs WHERE job_id = ?",
                String.class,
                jobId
        );
    }

    private org.springframework.security.test.web.servlet.request
            .SecurityMockMvcRequestPostProcessors.JwtRequestPostProcessor userJwt(
            UUID userId
    ) {
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

    private record Fixture(UUID userId, UUID sessionId) {
    }
}
