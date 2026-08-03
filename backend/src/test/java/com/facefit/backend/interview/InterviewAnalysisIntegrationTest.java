package com.facefit.backend.interview;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.facefit.backend.interview.application.AnswerAnalysisWorker;
import com.facefit.backend.interview.application.InterviewAnalysisOrchestrator;
import com.facefit.backend.interview.application.ReportGenerationWorker;
import com.facefit.backend.interview.integration.AnalysisResult;
import com.facefit.backend.interview.integration.ContentAnalysisPort;
import com.facefit.backend.interview.integration.CvAnalysisPort;
import com.facefit.backend.interview.integration.PortResult;
import com.facefit.backend.interview.integration.SttPort;
import com.facefit.backend.interview.integration.SttResult;
import com.facefit.backend.interview.integration.VoiceAnalysisPort;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "facefit.interview.processing.dispatch-enabled=false",
        "facefit.interview.processing.recovery-enabled=false"
})
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
class InterviewAnalysisIntegrationTest {

    private static final String SESSION_URI = "/api/v1/interview-sessions/";

    @Container
    static final PostgreSQLContainer<?> POSTGRESQL =
            new PostgreSQLContainer<>(DockerImageName.parse("postgres:16-alpine"))
                    .withDatabaseName("facefit")
                    .withUsername("facefit")
                    .withPassword("facefit")
                    .withInitScript("db/test-init-auth.sql");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
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
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private InterviewAnalysisOrchestrator orchestrator;

    @Autowired
    private AnswerAnalysisWorker answerWorker;

    @Autowired
    private ReportGenerationWorker reportWorker;

    @MockitoBean
    private JwtDecoder jwtDecoder;

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
        reset(sttPort, cvPort, voicePort, contentPort);
    }

    @Test
    void normalSessionMovesToAnalyzingButInterruptedAndMalformedSessionsDoNot() {
        Fixture normal = insertFixture("INTERVIEW_COMPLETED", "NORMAL", 10, true);
        orchestrator.orchestrate(normal.sessionId());
        assertThat(sessionStatus(normal.sessionId())).isEqualTo("ANALYZING");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT analysis_started_at IS NOT NULL FROM interview_sessions "
                        + "WHERE session_id = ?",
                Boolean.class,
                normal.sessionId()
        )).isTrue();

        Fixture interrupted = insertFixture("INTERRUPTED", "USER_INTERRUPTED", 0, false);
        orchestrator.orchestrate(interrupted.sessionId());
        assertThat(sessionStatus(interrupted.sessionId())).isEqualTo("INTERRUPTED");

        Fixture malformed = insertFixture("INTERVIEW_COMPLETED", "NORMAL", 9, true);
        orchestrator.orchestrate(malformed.sessionId());
        assertThat(sessionStatus(malformed.sessionId()))
                .isEqualTo("INTERVIEW_COMPLETED");
    }

    @Test
    void contentWaitsForItsOwnSttAndFailsWithoutCallingPortAfterDependencyFailure() {
        Fixture fixture = insertFixture("INTERVIEW_COMPLETED", "NORMAL", 10, true);
        orchestrator.orchestrate(fixture.sessionId());
        UUID answerId = answerId(fixture.sessionId(), 1);
        UUID contentJob = jobId(answerId, "CONTENT");

        answerWorker.process(contentJob);
        assertThat(jobStatus(contentJob)).isEqualTo("QUEUED");
        assertThat(attemptCount(contentJob)).isZero();
        verify(contentPort, never()).analyze(any());

        jdbcTemplate.update(
                """
                UPDATE interview_processing_jobs
                SET job_status = 'FAILED', failure_code = 'STT_FINAL_FAILURE',
                    failure_retryable = false, completed_at = now()
                WHERE answer_id = ? AND job_type = 'STT'
                """,
                answerId
        );
        answerWorker.process(contentJob);
        assertThat(jobStatus(contentJob)).isEqualTo("FAILED");
        assertThat(failureCode(contentJob)).isEqualTo("DEPENDENCY_FAILED");
        verify(contentPort, never()).analyze(any());
    }

    @Test
    void analysisStatusAggregatesJobsAndProtectsOwnershipAndInvalidStates()
            throws Exception {
        Fixture fixture = insertFixture("INTERVIEW_COMPLETED", "NORMAL", 10, true);
        orchestrator.orchestrate(fixture.sessionId());
        List<UUID> jobs = analysisJobIds(fixture.sessionId());
        for (int index = 0; index < 20; index++) {
            markJobSucceeded(jobs.get(index));
        }
        markJobFailed(jobs.get(20), "SAFE_FAILURE");

        mockMvc.perform(get(SESSION_URI + fixture.sessionId() + "/analysis-status")
                        .with(userJwt(fixture.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.sessionStatus").value("ANALYZING"))
                .andExpect(jsonPath("$.data.analysisStatus").value("FAILED"))
                .andExpect(jsonPath("$.data.progressPercent").value(50))
                .andExpect(jsonPath("$.data.failedAnswerCount").value(1))
                .andExpect(jsonPath("$.data.reportStatus")
                        .value("BLOCKED_BY_ANALYSIS_FAILURE"))
                .andExpect(jsonPath("$.data.errorCode")
                        .value("ANSWER_ANALYSIS_FAILED"))
                .andExpect(jsonPath("$.data.retryable").value(false))
                .andExpect(jsonPath("$.data.transcript").doesNotExist())
                .andExpect(jsonPath("$.data.workerToken").doesNotExist());

        UUID otherUser = insertProfile();
        mockMvc.perform(get(SESSION_URI + fixture.sessionId() + "/analysis-status")
                        .with(userJwt(otherUser)))
                .andExpect(status().isNotFound());
        mockMvc.perform(get(SESSION_URI + UUID.randomUUID() + "/analysis-status")
                        .with(userJwt(fixture.userId())))
                .andExpect(status().isNotFound());
        mockMvc.perform(get(SESSION_URI + fixture.sessionId() + "/analysis-status"))
                .andExpect(status().isUnauthorized());

        Fixture draft = insertFixture("DRAFT", null, 0, false);
        mockMvc.perform(get(SESSION_URI + draft.sessionId() + "/analysis-status")
                        .with(userJwt(draft.userId())))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("INVALID_STATE"));
        Fixture interrupted = insertFixture("INTERRUPTED", "USER_INTERRUPTED", 0, false);
        mockMvc.perform(get(
                        SESSION_URI + interrupted.sessionId() + "/analysis-status"
                ).with(userJwt(interrupted.userId())))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("INVALID_STATE"));
    }

    @Test
    void allAnalysisProducesOneDeterministicReportAndCompletesAtomically()
            throws Exception {
        Fixture fixture = insertFixture("INTERVIEW_COMPLETED", "NORMAL", 10, true);
        orchestrator.orchestrate(fixture.sessionId());
        stubSuccessfulAnalysis();

        for (int order = 1; order <= 10; order++) {
            UUID answerId = answerId(fixture.sessionId(), order);
            answerWorker.process(jobId(answerId, "STT"));
            answerWorker.process(jobId(answerId, "CV"));
            answerWorker.process(jobId(answerId, "VOICE"));
            answerWorker.process(jobId(answerId, "CONTENT"));
        }

        UUID reportJob = reportJobId(fixture.sessionId());
        reportWorker.process(reportJob);
        reportWorker.process(reportJob);
        orchestrator.orchestrate(fixture.sessionId());

        assertThat(sessionStatus(fixture.sessionId())).isEqualTo("COMPLETED");
        assertThat(count(
                "SELECT count(*) FROM interview_reports WHERE session_id = ?",
                fixture.sessionId()
        )).isEqualTo(1);
        assertThat(count(
                "SELECT count(*) FROM interview_processing_jobs "
                        + "WHERE session_id = ? AND job_type = 'REPORT_GENERATION'",
                fixture.sessionId()
        )).isEqualTo(1);
        assertThat(jobStatus(reportJob)).isEqualTo("SUCCEEDED");

        mockMvc.perform(get(SESSION_URI + fixture.sessionId() + "/report")
                        .with(userJwt(fixture.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.sessionStatus").value("COMPLETED"))
                .andExpect(jsonPath("$.data.reportStatus").value("SUCCEEDED"))
                .andExpect(jsonPath("$.data.report.schemaVersion").value("1.0"))
                .andExpect(jsonPath("$.data.report.scores.gaze").value(75.5))
                .andExpect(jsonPath("$.data.report.scores.posture").value(65.5))
                .andExpect(jsonPath("$.data.report.scores.speech").value(85.5))
                .andExpect(jsonPath("$.data.report.scores.content").value(55.5))
                .andExpect(jsonPath("$.data.report.overallScore").value(70.5))
                .andExpect(jsonPath("$.data.report.strengths[0].axis")
                        .value("SPEECH"))
                .andExpect(jsonPath("$.data.report.strengths[1].axis")
                        .value("GAZE"))
                .andExpect(jsonPath("$.data.report.improvements[0].axis")
                        .value("CONTENT"))
                .andExpect(jsonPath("$.data.report.improvements[1].axis")
                        .value("POSTURE"))
                .andExpect(jsonPath("$.data.report.questionFeedback.length()")
                        .value(10))
                .andExpect(jsonPath("$.data.report.inputHash").doesNotExist())
                .andExpect(jsonPath("$.data.report.transcript").doesNotExist())
                .andExpect(jsonPath("$.data.report.storagePath").doesNotExist())
                .andExpect(jsonPath("$.data.report.workerToken").doesNotExist());

        mockMvc.perform(get(SESSION_URI + fixture.sessionId() + "/analysis-status")
                        .with(userJwt(fixture.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.analysisStatus").value("SUCCEEDED"))
                .andExpect(jsonPath("$.data.progressPercent").value(100))
                .andExpect(jsonPath("$.data.completedAnswerCount").value(10))
                .andExpect(jsonPath("$.data.reportStatus").value("SUCCEEDED"));
    }

    @Test
    void declinedVoiceAnalysisSkipsVoiceAndStillProducesReport() throws Exception {
        Fixture fixture = insertFixture(
                "INTERVIEW_COMPLETED",
                "NORMAL",
                10,
                true,
                false
        );
        orchestrator.orchestrate(fixture.sessionId());
        stubSuccessfulAnalysis();

        for (int order = 1; order <= 10; order++) {
            UUID answerId = answerId(fixture.sessionId(), order);
            answerWorker.process(jobId(answerId, "STT"));
            answerWorker.process(jobId(answerId, "CV"));
            answerWorker.process(jobId(answerId, "CONTENT"));
        }
        verify(voicePort, never()).analyze(any());

        reportWorker.process(reportJobId(fixture.sessionId()));

        mockMvc.perform(get(SESSION_URI + fixture.sessionId() + "/report")
                        .with(userJwt(fixture.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.sessionStatus").value("COMPLETED"))
                .andExpect(jsonPath("$.data.report.scores.speech").doesNotExist())
                .andExpect(jsonPath("$.data.report.overallScore").value(65.5))
                .andExpect(jsonPath(
                        "$.data.report.questionFeedback[0].voiceAnalysisEnabled"
                ).value(false));

        mockMvc.perform(get(SESSION_URI + fixture.sessionId() + "/analysis-status")
                        .with(userJwt(fixture.userId())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.progressPercent").value(100))
                .andExpect(jsonPath("$.data.stages.voice.total").value(0));
    }

    @Test
    void reportEndpointDistinguishesWaitingAnalysisFailureGenerationFailureAndInterruption()
            throws Exception {
        Fixture waiting = insertFixture("INTERVIEW_COMPLETED", "NORMAL", 10, true);
        orchestrator.orchestrate(waiting.sessionId());
        mockMvc.perform(get(SESSION_URI + waiting.sessionId() + "/report")
                        .with(userJwt(waiting.userId())))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.reportStatus")
                        .value("WAITING_FOR_ANALYSIS"))
                .andExpect(jsonPath("$.data.report").isEmpty());

        markJobFailed(analysisJobIds(waiting.sessionId()).getFirst(), "SAFE_FAILURE");
        mockMvc.perform(get(SESSION_URI + waiting.sessionId() + "/report")
                        .with(userJwt(waiting.userId())))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code")
                        .value("REPORT_BLOCKED_BY_ANALYSIS_FAILURE"));

        Fixture reportFailure = insertFixture(
                "INTERVIEW_COMPLETED",
                "NORMAL",
                10,
                true
        );
        orchestrator.orchestrate(reportFailure.sessionId());
        analysisJobIds(reportFailure.sessionId()).forEach(this::markJobSucceeded);
        orchestrator.orchestrate(reportFailure.sessionId());
        reportWorker.process(reportJobId(reportFailure.sessionId()));
        mockMvc.perform(get(SESSION_URI + reportFailure.sessionId() + "/report")
                        .with(userJwt(reportFailure.userId())))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error.code")
                        .value("REPORT_GENERATION_FAILED"));

        Fixture interrupted = insertFixture("INTERRUPTED", "USER_INTERRUPTED", 0, false);
        mockMvc.perform(get(SESSION_URI + interrupted.sessionId() + "/report")
                        .with(userJwt(interrupted.userId())))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("REPORT_NOT_AVAILABLE"));
    }

    @Test
    void invalidScoresRetryThenFailWithoutPersistingResultsOrReport() {
        Fixture fixture = insertFixture("INTERVIEW_COMPLETED", "NORMAL", 10, true);
        orchestrator.orchestrate(fixture.sessionId());
        var payload = objectMapper.createObjectNode();
        payload.put("schemaVersion", "1.0");
        payload.put("gazeScore", 101);
        payload.put("postureScore", 80);
        payload.putArray("feedback");
        when(cvPort.analyze(any()))
                .thenReturn(PortResult.success(new AnalysisResult(payload)));
        UUID cvJob = jobId(answerId(fixture.sessionId(), 1), "CV");

        for (int attempt = 0; attempt < 3; attempt++) {
            answerWorker.process(cvJob);
            jdbcTemplate.update(
                    "UPDATE interview_processing_jobs SET next_retry_at = now() "
                            + "WHERE job_id = ?",
                    cvJob
            );
        }

        assertThat(jobStatus(cvJob)).isEqualTo("FAILED");
        assertThat(failureCode(cvJob)).isEqualTo("ANALYSIS_RESPONSE_INVALID");
        assertThat(count(
                "SELECT count(*) FROM interview_analysis_results "
                        + "WHERE source_job_id = ?",
                cvJob
        )).isZero();
        assertThat(count(
                "SELECT count(*) FROM interview_processing_jobs "
                        + "WHERE session_id = ? AND job_type = 'REPORT_GENERATION'",
                fixture.sessionId()
        )).isZero();
    }

    @Test
    void concurrentOrchestrationRegistersOnlyOneReportJob() throws Exception {
        Fixture fixture = insertFixture("INTERVIEW_COMPLETED", "NORMAL", 10, true);
        orchestrator.orchestrate(fixture.sessionId());
        analysisJobIds(fixture.sessionId()).forEach(this::markJobSucceeded);

        CountDownLatch start = new CountDownLatch(1);
        try (var executor = Executors.newFixedThreadPool(2)) {
            var first = executor.submit(() -> {
                start.await();
                orchestrator.orchestrate(fixture.sessionId());
                return true;
            });
            var second = executor.submit(() -> {
                start.await();
                orchestrator.orchestrate(fixture.sessionId());
                return true;
            });
            start.countDown();
            assertThat(first.get(10, TimeUnit.SECONDS)).isTrue();
            assertThat(second.get(10, TimeUnit.SECONDS)).isTrue();
        }

        assertThat(count(
                "SELECT count(*) FROM interview_processing_jobs "
                        + "WHERE session_id = ? AND job_type = 'REPORT_GENERATION'",
                fixture.sessionId()
        )).isEqualTo(1);
    }

    private void stubSuccessfulAnalysis() {
        when(sttPort.transcribe(any())).thenAnswer(invocation -> {
            var request = (com.facefit.backend.interview.integration
                    .AnswerAnalysisRequest) invocation.getArgument(0);
            return PortResult.success(new SttResult(
                    "1.0",
                    "비공개 전사문 " + order(request.questionText())
            ));
        });
        when(cvPort.analyze(any())).thenAnswer(invocation -> {
            var request = (com.facefit.backend.interview.integration
                    .AnswerAnalysisRequest) invocation.getArgument(0);
            int order = order(request.questionText());
            var payload = objectMapper.createObjectNode();
            payload.put("schemaVersion", "1.0");
            payload.put("gazeScore", 70 + order);
            payload.put("postureScore", 60 + order);
            payload.putArray("feedback").add("공개 CV 피드백 " + order);
            return PortResult.success(new AnalysisResult(payload));
        });
        when(voicePort.analyze(any())).thenAnswer(invocation -> {
            var request = (com.facefit.backend.interview.integration
                    .AnswerAnalysisRequest) invocation.getArgument(0);
            int order = order(request.questionText());
            var payload = objectMapper.createObjectNode();
            payload.put("schemaVersion", "1.0");
            payload.put("speechScore", 80 + order);
            payload.putArray("feedback").add("공개 음성 피드백 " + order);
            return PortResult.success(new AnalysisResult(payload));
        });
        when(contentPort.analyze(any())).thenAnswer(invocation -> {
            var request = (com.facefit.backend.interview.integration
                    .AnswerAnalysisRequest) invocation.getArgument(0);
            int order = order(request.questionText());
            var payload = objectMapper.createObjectNode();
            payload.put("schemaVersion", "1.0");
            payload.put("contentScore", 50 + order);
            payload.putArray("feedback").add("공개 내용 피드백 " + order);
            return PortResult.success(new AnalysisResult(payload));
        });
    }

    private int order(String questionText) {
        return Integer.parseInt(questionText.substring(1));
    }

    private Fixture insertFixture(
            String status,
            String completionType,
            int answerCount,
            boolean createAnalysisJobs
    ) {
        return insertFixture(
                status,
                completionType,
                answerCount,
                createAnalysisJobs,
                true
        );
    }

    private Fixture insertFixture(
            String status,
            String completionType,
            int answerCount,
            boolean createAnalysisJobs,
            boolean voiceAnalysisEnabled
    ) {
        UUID userId = insertProfile();
        UUID documentId = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO career_documents (
                    document_id, user_id, document_type, original_file_name,
                    storage_bucket, storage_path, mime_type, file_size_bytes,
                    processing_status, extracted_text
                ) VALUES (?, ?, 'RESUME', 'resume.pdf', 'career-documents', ?,
                          'application/pdf', 100, 'READY', 'resume text')
                """,
                documentId,
                userId,
                userId + "/" + documentId + ".pdf"
        );
        UUID postingId = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO job_postings (
                    job_posting_id, user_id, input_type, raw_text,
                    company_name, target_role, main_responsibilities,
                    qualifications, processing_status
                ) VALUES (?, ?, 'TEXT', 'posting', 'FaceFit', 'Backend',
                          'API', 'Java', 'READY')
                """,
                postingId,
                userId
        );
        UUID sessionId = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO interview_sessions (
                    session_id, user_id, resume_document_id, job_posting_id,
                    persona, difficulty, session_status, completion_type,
                    voice_analysis_enabled,
                    snapshot_company_name, snapshot_target_role,
                    snapshot_main_responsibilities, snapshot_qualifications,
                    started_at, interview_completed_at, interrupted_at,
                    analysis_started_at
                ) VALUES (
                    ?, ?, ?, ?, 'TECHNICAL_MANAGER', 'NORMAL', ?, ?, ?,
                    'FaceFit', 'Backend', 'API', 'Java',
                    CASE WHEN ? IN ('IN_PROGRESS', 'INTERVIEW_COMPLETED',
                        'ANALYZING', 'COMPLETED', 'INTERRUPTED') THEN now() END,
                    CASE WHEN ? IN ('INTERVIEW_COMPLETED', 'ANALYZING',
                        'COMPLETED') THEN now() END,
                    CASE WHEN ? = 'INTERRUPTED' THEN now() END,
                    CASE WHEN ? IN ('ANALYZING', 'COMPLETED') THEN now() END
                )
                """,
                sessionId,
                userId,
                documentId,
                postingId,
                status,
                completionType,
                voiceAnalysisEnabled,
                status,
                status,
                status,
                status
        );
        UUID generationJobId = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO interview_processing_jobs (
                    job_id, session_id, job_type, job_status,
                    attempt_count, completed_at
                ) VALUES (?, ?, 'QUESTION_GENERATION', 'SUCCEEDED', 1, now())
                """,
                generationJobId,
                sessionId
        );
        for (int order = 1; order <= 10; order++) {
            UUID turnId = UUID.randomUUID();
            jdbcTemplate.update(
                    """
                    INSERT INTO interview_turns (
                        turn_id, session_id, generation_job_id, question_order,
                        question_type, question_category, question_text
                    ) VALUES (?, ?, ?, ?, ?, 'category', ?)
                    """,
                    turnId,
                    sessionId,
                    generationJobId,
                    order,
                    questionType(order),
                    "Q" + order
            );
            if (order <= answerCount) {
                UUID answerId = UUID.randomUUID();
                jdbcTemplate.update(
                        """
                        INSERT INTO interview_answers (
                            answer_id, session_id, turn_id, user_id,
                            storage_bucket, storage_path, mime_type,
                            file_size_bytes, file_sha256,
                            recorded_duration_seconds, detected_duration_millis,
                            ended_by, answer_status, next_question_ready,
                            confirmed_at
                        ) VALUES (
                            ?, ?, ?, ?, 'interview-answers', ?, 'video/mp4',
                            100, ?, 30, 30000, 'USER_BUTTON', 'QUEUED', true, now()
                        )
                        """,
                        answerId,
                        sessionId,
                        turnId,
                        userId,
                        "sessions/" + sessionId + "/answers/" + answerId + ".mp4",
                        "a".repeat(64)
                );
                if (createAnalysisJobs) {
                    List<String> types = voiceAnalysisEnabled
                            ? List.of("STT", "CV", "VOICE", "CONTENT")
                            : List.of("STT", "CV", "CONTENT");
                    for (String type : types) {
                        jdbcTemplate.update(
                                """
                                INSERT INTO interview_processing_jobs (
                                    job_id, session_id, answer_id, job_type
                                ) VALUES (?, ?, ?, ?)
                                """,
                                UUID.randomUUID(),
                                sessionId,
                                answerId,
                                type
                        );
                    }
                }
            }
        }
        return new Fixture(userId, sessionId);
    }

    private UUID insertProfile() {
        UUID userId = UUID.randomUUID();
        jdbcTemplate.update("INSERT INTO auth.users (id) VALUES (?)", userId);
        jdbcTemplate.update(
                """
                INSERT INTO profiles (
                    user_id, member_status, onboarding_status,
                    onboarding_completed_at, voice_analysis_consent,
                    voice_analysis_consented_at
                ) VALUES (?, 'ACTIVE', 'COMPLETED', now(), true, now())
                """,
                userId
        );
        return userId;
    }

    private String questionType(int order) {
        if (order == 1) {
            return "INTRODUCTION";
        }
        if (order <= 4) {
            return "EXPERIENCE";
        }
        if (order <= 7) {
            return "JOB_ROLE";
        }
        if (order <= 9) {
            return "BEHAVIORAL";
        }
        return "CLOSING";
    }

    private UUID answerId(UUID sessionId, int order) {
        return jdbcTemplate.queryForObject(
                """
                SELECT a.answer_id
                FROM interview_answers a
                JOIN interview_turns t ON t.turn_id = a.turn_id
                WHERE a.session_id = ? AND t.question_order = ?
                """,
                UUID.class,
                sessionId,
                order
        );
    }

    private UUID jobId(UUID answerId, String type) {
        return jdbcTemplate.queryForObject(
                "SELECT job_id FROM interview_processing_jobs "
                        + "WHERE answer_id = ? AND job_type = ?",
                UUID.class,
                answerId,
                type
        );
    }

    private UUID reportJobId(UUID sessionId) {
        return jdbcTemplate.queryForObject(
                "SELECT job_id FROM interview_processing_jobs "
                        + "WHERE session_id = ? AND job_type = 'REPORT_GENERATION'",
                UUID.class,
                sessionId
        );
    }

    private List<UUID> analysisJobIds(UUID sessionId) {
        return jdbcTemplate.queryForList(
                """
                SELECT job_id FROM interview_processing_jobs
                WHERE session_id = ?
                  AND job_type IN ('STT', 'CV', 'VOICE', 'CONTENT')
                ORDER BY answer_id, job_type
                """,
                UUID.class,
                sessionId
        );
    }

    private void markJobSucceeded(UUID jobId) {
        jdbcTemplate.update(
                """
                UPDATE interview_processing_jobs
                SET job_status = 'SUCCEEDED', completed_at = now(),
                    worker_token = null, locked_at = null
                WHERE job_id = ?
                """,
                jobId
        );
    }

    private void markJobFailed(UUID jobId, String code) {
        jdbcTemplate.update(
                """
                UPDATE interview_processing_jobs
                SET job_status = 'FAILED', completed_at = now(),
                    failure_code = ?, failure_retryable = false,
                    worker_token = null, locked_at = null
                WHERE job_id = ?
                """,
                code,
                jobId
        );
    }

    private String sessionStatus(UUID sessionId) {
        return jdbcTemplate.queryForObject(
                "SELECT session_status FROM interview_sessions WHERE session_id = ?",
                String.class,
                sessionId
        );
    }

    private String jobStatus(UUID jobId) {
        return jdbcTemplate.queryForObject(
                "SELECT job_status FROM interview_processing_jobs WHERE job_id = ?",
                String.class,
                jobId
        );
    }

    private int attemptCount(UUID jobId) {
        return jdbcTemplate.queryForObject(
                "SELECT attempt_count FROM interview_processing_jobs WHERE job_id = ?",
                Integer.class,
                jobId
        );
    }

    private String failureCode(UUID jobId) {
        return jdbcTemplate.queryForObject(
                "SELECT failure_code FROM interview_processing_jobs WHERE job_id = ?",
                String.class,
                jobId
        );
    }

    private int count(String sql, UUID id) {
        return jdbcTemplate.queryForObject(sql, Integer.class, id);
    }

    private org.springframework.security.test.web.servlet.request
            .SecurityMockMvcRequestPostProcessors.JwtRequestPostProcessor userJwt(
            UUID userId
    ) {
        return jwt().jwt(token -> token
                .subject(userId.toString())
                .claim("role", "authenticated"));
    }

    private record Fixture(UUID userId, UUID sessionId) {
    }
}
