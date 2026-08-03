package com.facefit.backend.jobposting;

import com.facefit.backend.jobposting.application.JobPostingFileFormat;
import com.facefit.backend.jobposting.application.JobPostingProcessingWorker;
import com.facefit.backend.jobposting.application.JobPostingService;
import com.facefit.backend.jobposting.application.JobProcessingException;
import com.facefit.backend.jobposting.extraction.JobPostingTextExtractionService;
import com.facefit.backend.jobposting.storage.JobPostingStorage;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.time.OffsetDateTime;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringBootTest
@Testcontainers(disabledWithoutDocker = true)
class JobPostingProcessingWorkerIntegrationTest {

    private static final String STRUCTURED_TEXT = """
            회사명: FaceFit
            모집 직무: 백엔드 개발자
            주요 업무: API 설계
            자격요건: Java 경험
            우대사항: PostgreSQL 경험
            """;

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
        registry.add("facefit.job-postings.processing.stale-minutes", () -> 15);
    }

    @Autowired
    private JobPostingProcessingWorker worker;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private JobPostingService service;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @MockitoBean
    private JobPostingStorage storage;

    @MockitoBean
    private JobPostingTextExtractionService extractionService;

    private UUID owner;

    @BeforeEach
    void clearDatabase() {
        jdbcTemplate.execute(
                "TRUNCATE TABLE job_postings, career_documents, user_legal_records, "
                        + "legal_documents, profiles, auth.users CASCADE"
        );
        reset(storage, extractionService);
        owner = insertCompletedProfile();
    }

    @Test
    void textPostingBecomesReadyWithoutStorage() {
        UUID id = insertTextPosting(STRUCTURED_TEXT, "PROCESSING", 0, null, null);

        worker.process(id);

        assertState(id, "READY", 1, null);
        assertThat(value(id, "company_name")).isEqualTo("FaceFit");
        assertThat(value(id, "target_role")).isEqualTo("백엔드 개발자");
        assertThat(value(id, "extracted_text")).contains("PostgreSQL");
        verify(storage, never()).download(any(), any());
    }

    @Test
    void filePostingDownloadsThenUsesFormatSpecificExtractor() {
        UUID id = insertFilePosting(
                "application/x-hwp-v5",
                "owner/posting.hwp",
                "PROCESSING",
                0,
                null,
                null
        );
        byte[] content = {1, 2, 3};
        when(storage.download("job-postings", "owner/posting.hwp")).thenReturn(content);
        when(extractionService.extract(JobPostingFileFormat.HWP5, content))
                .thenReturn(STRUCTURED_TEXT);

        worker.process(id);

        assertState(id, "READY", 1, null);
        verify(storage).download("job-postings", "owner/posting.hwp");
        verify(extractionService).extract(JobPostingFileFormat.HWP5, content);
    }

    @Test
    void incompleteStructureFailsButPreservesPartialExtraction() {
        UUID id = insertTextPosting(
                "회사명: FaceFit\n모집 직무: 백엔드 개발자",
                "PROCESSING",
                0,
                null,
                null
        );

        worker.process(id);

        assertState(id, "FAILED", 1, "STRUCTURED_FIELDS_INCOMPLETE");
        assertThat(value(id, "company_name")).isEqualTo("FaceFit");
        assertThat(value(id, "qualifications")).isNull();
    }

    @Test
    void emptyExtractionUsesStableFailureCode() {
        UUID id = insertTextPosting(" \n\t ", "PROCESSING", 0, null, null);

        worker.process(id);

        assertState(id, "FAILED", 1, "EXTRACTED_TEXT_EMPTY");
    }

    @Test
    void transientFailureRetriesAndThenSucceedsIdempotently() {
        UUID id = insertFilePosting(
                "image/png",
                "owner/posting.png",
                "PROCESSING",
                0,
                null,
                null
        );
        byte[] content = {1, 2, 3};
        when(storage.download("job-postings", "owner/posting.png")).thenReturn(content);
        when(extractionService.extract(JobPostingFileFormat.PNG, content))
                .thenThrow(new JobProcessingException("OCR_TIMEOUT", true))
                .thenReturn(STRUCTURED_TEXT);

        worker.process(id);
        worker.process(id);

        assertState(id, "READY", 2, null);
        verify(extractionService, times(2)).extract(JobPostingFileFormat.PNG, content);
    }

    @Test
    void retryableFailureStopsAtThreeAttemptsAndFails() {
        UUID id = insertFilePosting(
                "application/pdf",
                "owner/posting.pdf",
                "PROCESSING",
                0,
                null,
                null
        );
        byte[] content = {1, 2, 3};
        when(storage.download("job-postings", "owner/posting.pdf")).thenReturn(content);
        when(extractionService.extract(JobPostingFileFormat.PDF, content))
                .thenThrow(new JobProcessingException("OCR_TIMEOUT", true));

        worker.process(id);

        assertState(id, "FAILED", 3, "OCR_TIMEOUT");
        verify(extractionService, times(3)).extract(JobPostingFileFormat.PDF, content);
    }

    @Test
    void nonRetryableHwpExtractionFailureFailsAtFirstAttempt() {
        UUID id = insertFilePosting(
                "application/x-hwp-v5",
                "owner/posting.hwp",
                "PROCESSING",
                0,
                null,
                null
        );
        byte[] content = {1, 2, 3};
        when(storage.download(any(), any())).thenReturn(content);
        when(extractionService.extract(eq(JobPostingFileFormat.HWP5), any()))
                .thenThrow(new JobProcessingException("HWP_EXTRACTION_FAILED", false));

        worker.process(id);

        assertState(id, "FAILED", 1, "HWP_EXTRACTION_FAILED");
    }

    @Test
    void staleProcessingClaimCanBeRecovered() {
        UUID id = insertTextPosting(
                STRUCTURED_TEXT,
                "PROCESSING",
                1,
                OffsetDateTime.now().minusHours(1),
                null
        );

        worker.process(id);

        assertState(id, "READY", 2, null);
    }

    @Test
    void activeClaimReadyAndDeletedRowsAreNotProcessedAgain() {
        UUID activeClaim = insertTextPosting(
                STRUCTURED_TEXT,
                "PROCESSING",
                1,
                OffsetDateTime.now(),
                null
        );
        UUID ready = insertTextPosting(STRUCTURED_TEXT, "READY", 1, null, null);
        UUID deleted = insertTextPosting(
                STRUCTURED_TEXT,
                "PROCESSING",
                0,
                null,
                OffsetDateTime.now()
        );

        worker.process(activeClaim);
        worker.process(ready);
        worker.process(deleted);

        assertState(activeClaim, "PROCESSING", 1, null);
        assertState(ready, "READY", 1, null);
        assertState(deleted, "PROCESSING", 0, null);
    }

    @Test
    void deleteWinningRacePreventsWorkerFromRestoringReadyState() throws Exception {
        UUID id = insertFilePosting(
                "application/pdf",
                "owner/racing.pdf",
                "PROCESSING",
                0,
                null,
                null
        );
        byte[] content = {1, 2, 3};
        CountDownLatch extractionStarted = new CountDownLatch(1);
        CountDownLatch finishExtraction = new CountDownLatch(1);
        when(storage.download("job-postings", "owner/racing.pdf")).thenReturn(content);
        when(extractionService.extract(JobPostingFileFormat.PDF, content))
                .thenAnswer(invocation -> {
                    extractionStarted.countDown();
                    if (!finishExtraction.await(5, TimeUnit.SECONDS)) {
                        throw new JobProcessingException("TEST_TIMEOUT", false);
                    }
                    return STRUCTURED_TEXT;
                });

        try (ExecutorService executor = Executors.newSingleThreadExecutor()) {
            Future<?> processing = executor.submit(() -> worker.process(id));
            assertThat(extractionStarted.await(5, TimeUnit.SECONDS)).isTrue();
            service.delete(jwtToken(owner), id);
            finishExtraction.countDown();
            processing.get(10, TimeUnit.SECONDS);
        }

        assertThat(jdbcTemplate.queryForObject(
                "SELECT deleted_at IS NOT NULL FROM job_postings WHERE job_posting_id = ?",
                Boolean.class,
                id
        )).isTrue();
        assertState(id, "PROCESSING", 1, null);
        verify(storage).delete("job-postings", "owner/racing.pdf");
    }

    private void assertState(UUID id, String status, int attempts, String error) {
        assertThat(value(id, "processing_status")).isEqualTo(status);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT processing_attempt_count FROM job_postings WHERE job_posting_id = ?",
                Integer.class,
                id
        )).isEqualTo(attempts);
        assertThat(value(id, "processing_error")).isEqualTo(error);
    }

    private String value(UUID id, String column) {
        return jdbcTemplate.queryForObject(
                "SELECT " + column + " FROM job_postings WHERE job_posting_id = ?",
                String.class,
                id
        );
    }

    private UUID insertCompletedProfile() {
        UUID userId = UUID.randomUUID();
        jdbcTemplate.update("INSERT INTO auth.users (id) VALUES (?)", userId);
        jdbcTemplate.update(
                """
                INSERT INTO profiles (
                  user_id, member_status, onboarding_status, onboarding_completed_at
                ) VALUES (?, 'ACTIVE', 'COMPLETED', ?)
                """,
                userId,
                OffsetDateTime.now()
        );
        return userId;
    }

    private UUID insertTextPosting(
            String rawText,
            String status,
            int attempts,
            OffsetDateTime startedAt,
            OffsetDateTime deletedAt
    ) {
        UUID id = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO job_postings (
                  job_posting_id, user_id, input_type, raw_text, processing_status,
                  processing_attempt_count, processing_started_at, deleted_at
                ) VALUES (?, ?, 'TEXT', ?, ?, ?, ?, ?)
                """,
                id,
                owner,
                rawText,
                status,
                attempts,
                startedAt,
                deletedAt
        );
        return id;
    }

    private UUID insertFilePosting(
            String mimeType,
            String objectKey,
            String status,
            int attempts,
            OffsetDateTime startedAt,
            OffsetDateTime deletedAt
    ) {
        UUID id = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO job_postings (
                  job_posting_id, user_id, input_type, original_file_name,
                  storage_bucket, storage_path, mime_type, file_size_bytes,
                  processing_status, processing_attempt_count, processing_started_at, deleted_at
                ) VALUES (?, ?, 'FILE', 'posting.bin', 'job-postings', ?, ?, 3, ?, ?, ?, ?)
                """,
                id,
                owner,
                objectKey,
                mimeType,
                status,
                attempts,
                startedAt,
                deletedAt
        );
        return id;
    }

    private Jwt jwtToken(UUID userId) {
        Instant now = Instant.now();
        return Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject(userId.toString())
                .issuedAt(now)
                .expiresAt(now.plusSeconds(300))
                .build();
    }
}
