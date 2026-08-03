package com.facefit.backend.jobposting;

import com.facefit.backend.common.exception.StorageOperationException;
import com.facefit.backend.jobposting.application.JobPostingObjectKeyFactory;
import com.facefit.backend.jobposting.application.JobPostingService;
import com.facefit.backend.common.exception.ResourceNotFoundException;
import com.facefit.backend.jobposting.storage.JobPostingStorage;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.poi.poifs.filesystem.DirectoryEntry;
import org.apache.poi.poifs.filesystem.POIFSFileSystem;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.Instant;
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
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
class JobPostingIntegrationTest {

    private static final String URI = "/api/v1/job-postings";

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
        registry.add(
                "facefit.storage.supabase.job-postings-bucket",
                () -> "job-postings"
        );
        registry.add("facefit.job-postings.processing.async-enabled", () -> false);
        registry.add("facefit.job-postings.processing.recovery-enabled", () -> false);
        registry.add("facefit.job-postings.ocr.enabled", () -> false);
    }

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private JobPostingService service;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @MockitoBean
    private JobPostingStorage storage;

    @MockitoBean
    private JobPostingObjectKeyFactory objectKeyFactory;

    @BeforeEach
    void clearDatabase() {
        jdbcTemplate.execute(
                "TRUNCATE TABLE job_postings, career_documents, user_legal_records, "
                        + "legal_documents, profiles, auth.users CASCADE"
        );
        reset(storage, objectKeyFactory);
        when(objectKeyFactory.create(any(), any(), anyString()))
                .thenAnswer(invocation -> "%s/%s/%s.%s".formatted(
                        invocation.getArgument(0),
                        invocation.getArgument(1),
                        UUID.randomUUID(),
                        invocation.getArgument(2)
                ));
    }

    @Test
    void everyEndpointRequiresAuthentication() throws Exception {
        UUID id = UUID.randomUUID();
        mockMvc.perform(post(URI)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(textBody("TEXT", "회사명: FaceFit")))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(get(URI)).andExpect(status().isUnauthorized());
        mockMvc.perform(get(URI + "/" + id)).andExpect(status().isUnauthorized());
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .patch(URI + "/" + id)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"companyName\":\"FaceFit\"}"))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                        .delete(URI + "/" + id))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void inactiveAndIncompleteMembersCannotRegister() throws Exception {
        UUID blocked = insertProfile("BLOCKED", "COMPLETED");
        UUID incomplete = insertProfile("ACTIVE", "NOT_STARTED");

        createText(blocked, "TEXT", "회사명: FaceFit")
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("MEMBER_ACCESS_DENIED"));
        createText(incomplete, "TEXT", "회사명: FaceFit")
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("ONBOARDING_REQUIRED"));
        assertThat(postingCount()).isZero();
    }

    @Test
    void textRegistrationStoresOnlyRawTextAndReturnsProcessing() throws Exception {
        UUID userId = insertCompletedProfile();
        String rawText = "<script>alert('not executed')</script>\n회사명: FaceFit";

        createText(userId, "TEXT", rawText)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.processingStatus").value("PROCESSING"))
                .andExpect(jsonPath("$.data.jobPostingId").isNotEmpty());

        assertThat(jdbcTemplate.queryForObject(
                "SELECT input_type FROM job_postings",
                String.class
        )).isEqualTo("TEXT");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT raw_text FROM job_postings",
                String.class
        )).isEqualTo(rawText);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT storage_path IS NULL FROM job_postings",
                Boolean.class
        )).isTrue();
        verify(storage, never()).upload(anyString(), anyString(), anyString(), any());
    }

    @Test
    void textLengthAcceptsBoundaryAndRejectsOverLimit() throws Exception {
        UUID userId = insertCompletedProfile();

        createText(userId, "TEXT", "가".repeat(50_000))
                .andExpect(status().isOk());
        createText(userId, "TEXT", "가".repeat(50_001))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));

        assertThat(postingCount()).isOne();
    }

    @Test
    void fileAndTextModesAreStrictlyMutuallyExclusive() throws Exception {
        UUID userId = insertCompletedProfile();

        createText(userId, "FILE", "회사명: FaceFit")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("UNSUPPORTED_INPUT_TYPE"));
        upload(userId, "TEXT", pdfFile(), null)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("UNSUPPORTED_INPUT_TYPE"));
        upload(userId, "FILE", pdfFile(), "회사명: FaceFit")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("UNSUPPORTED_INPUT_TYPE"));
        createText(userId, "TEXT", " ")
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_REQUEST"));
        mockMvc.perform(post(URI)
                        .contentType(MediaType.TEXT_PLAIN)
                        .content("text")
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.error.code").value("UNSUPPORTED_MEDIA_TYPE"));
        assertThat(postingCount()).isZero();
    }

    @Test
    void validPdfAndHwpFilesUploadToPrivateStorageWithNormalizedMetadata() throws Exception {
        UUID userId = insertCompletedProfile();

        upload(userId, "FILE", pdfFile(), null)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.processingStatus").value("PROCESSING"))
                .andExpect(jsonPath("$.data.storagePath").doesNotExist());
        MockMultipartFile hwp = new MockMultipartFile(
                "file",
                "../../posting.hwp",
                "application/vnd.hancom.hwp",
                hwp5()
        );
        upload(userId, "FILE", hwp, null)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.processingStatus").value("PROCESSING"));

        assertThat(jdbcTemplate.queryForList(
                "SELECT original_file_name FROM job_postings ORDER BY original_file_name",
                String.class
        )).containsExactlyInAnyOrder("posting.pdf", "posting.hwp");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT mime_type FROM job_postings WHERE original_file_name = 'posting.hwp'",
                String.class
        )).isEqualTo("application/x-hwp-v5");
        verify(storage).upload(eq("job-postings"), anyString(), eq("application/pdf"), any());
        verify(storage).upload(
                eq("job-postings"),
                anyString(),
                eq("application/x-hwp-v5"),
                any()
        );
    }

    @Test
    void invalidFileNeverReachesStorageOrDatabase() throws Exception {
        UUID userId = insertCompletedProfile();
        MockMultipartFile disguised = new MockMultipartFile(
                "file",
                "posting.hwp",
                "application/x-hwp",
                "%PDF-not-hwp".getBytes(StandardCharsets.UTF_8)
        );

        upload(userId, "FILE", disguised, null)
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(jsonPath("$.error.code").value("FILE_TYPE_NOT_SUPPORTED"));

        assertThat(postingCount()).isZero();
        verify(storage, never()).upload(anyString(), anyString(), anyString(), any());
    }

    @Test
    void storageUploadFailureDoesNotLeaveDatabaseMetadata() throws Exception {
        UUID userId = insertCompletedProfile();
        doThrow(new StorageOperationException("upload failed"))
                .when(storage).upload(anyString(), anyString(), anyString(), any());

        upload(userId, "FILE", pdfFile(), null)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error.code").value("STORAGE_OPERATION_FAILED"));

        assertThat(postingCount()).isZero();
    }

    @Test
    void databaseFailureAfterUploadCompensatesStorageObject() throws Exception {
        UUID userId = insertCompletedProfile();
        String duplicateObjectKey = "fixed/object.pdf";
        insertPosting(userId, "FILE", "PROCESSING", duplicateObjectKey, null);
        when(objectKeyFactory.create(any(), any(), anyString())).thenReturn(duplicateObjectKey);

        upload(userId, "FILE", pdfFile(), null)
                .andExpect(status().is5xxServerError());

        verify(storage).delete("job-postings", duplicateObjectKey);
        assertThat(postingCount()).isOne();
    }

    @Test
    void listFiltersOwnerStatusSortsAndNeverExposesStorageOrRawPayload() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID older = insertPosting(owner, "TEXT", "FAILED", null, null);
        UUID newer = insertPosting(owner, "FILE", "READY", "owner/newer.pdf", null);
        insertPosting(other, "FILE", "READY", "other/hidden.pdf", null);
        insertPosting(owner, "FILE", "READY", "owner/deleted.pdf", OffsetDateTime.now());
        jdbcTemplate.update(
                "UPDATE job_postings SET created_at = ? WHERE job_posting_id = ?",
                OffsetDateTime.now().minusDays(1),
                older
        );
        jdbcTemplate.update(
                "UPDATE job_postings SET created_at = ? WHERE job_posting_id = ?",
                OffsetDateTime.now(),
                newer
        );

        mockMvc.perform(get(URI)
                        .param("processingStatus", "READY")
                        .param("page", "0")
                        .param("size", "10")
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.totalElements").value(1))
                .andExpect(jsonPath("$.data.content[0].jobPostingId").value(newer.toString()))
                .andExpect(jsonPath("$.data.content[0].storagePath").doesNotExist())
                .andExpect(jsonPath("$.data.content[0].rawText").doesNotExist())
                .andExpect(jsonPath("$.data.content[0].processingError").doesNotExist());
    }

    @Test
    void listRejectsInvalidPageSizeAndStatus() throws Exception {
        UUID owner = insertCompletedProfile();

        mockMvc.perform(get(URI)
                        .param("page", "-1")
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isBadRequest());
        mockMvc.perform(get(URI)
                        .param("size", "101")
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isBadRequest());
        mockMvc.perform(get(URI)
                        .param("processingStatus", "UNKNOWN")
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isBadRequest());
    }

    @Test
    void detailIsOwnerOnlyHidesStorageAndShowsOnlyAppropriateSourceText() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID textId = insertPosting(owner, "TEXT", "READY", null, null);
        UUID fileId = insertPosting(owner, "FILE", "READY", "owner/file.pdf", null);

        mockMvc.perform(get(URI + "/" + textId)
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.rawText").isNotEmpty())
                .andExpect(jsonPath("$.data.extractedText").doesNotExist())
                .andExpect(jsonPath("$.data.storagePath").doesNotExist());
        mockMvc.perform(get(URI + "/" + fileId)
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.rawText").doesNotExist())
                .andExpect(jsonPath("$.data.extractedText").isNotEmpty());
        assertNotFound(other, textId);
    }

    @Test
    void patchRejectsProcessingUnknownEmptyAndRequiredNullThenCompletesFailedPosting() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID processing = insertPosting(owner, "TEXT", "PROCESSING", null, null);
        UUID failed = insertPosting(owner, "TEXT", "FAILED", null, null);

        patch(owner, processing, "{\"companyName\":\"FaceFit\"}")
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.error.code").value("RESOURCE_NOT_READY"));
        patch(owner, failed, "{}")
                .andExpect(status().isBadRequest());
        patch(owner, failed, "{\"unknown\":\"value\"}")
                .andExpect(status().isBadRequest());
        patch(owner, failed, "{\"companyName\":null}")
                .andExpect(status().isBadRequest());

        patch(owner, failed, """
                {
                  "companyName":"FaceFit",
                  "targetRole":"백엔드 개발자",
                  "mainResponsibilities":"API 설계",
                  "qualifications":"Java 경험",
                  "preferredQualifications":null
                }
                """)
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.processingStatus").value("READY"))
                .andExpect(jsonPath("$.data.companyName").value("FaceFit"))
                .andExpect(jsonPath("$.data.preferredQualifications").doesNotExist());
    }

    @Test
    void deleteSoftDeletesTextWithoutStorageAndDeletesFileObject() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID textId = insertPosting(owner, "TEXT", "READY", null, null);
        UUID fileId = insertPosting(owner, "FILE", "READY", "owner/file.pdf", null);

        delete(owner, textId).andExpect(status().isNoContent());
        verify(storage, never()).delete("job-postings", null);
        delete(owner, fileId).andExpect(status().isNoContent());
        verify(storage).delete("job-postings", "owner/file.pdf");

        assertThat(jdbcTemplate.queryForObject(
                "SELECT count(*) FROM job_postings WHERE deleted_at IS NOT NULL",
                Long.class
        )).isEqualTo(2);
        assertNotFound(owner, textId);
        assertNotFound(owner, fileId);
    }

    @Test
    void storageDeleteFailureRestoresSoftDelete() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID fileId = insertPosting(owner, "FILE", "READY", "owner/file.pdf", null);
        doThrow(new StorageOperationException("delete failed"))
                .when(storage).delete("job-postings", "owner/file.pdf");

        delete(owner, fileId)
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error.code").value("STORAGE_OPERATION_FAILED"));

        assertThat(jdbcTemplate.queryForObject(
                "SELECT deleted_at IS NULL FROM job_postings WHERE job_posting_id = ?",
                Boolean.class,
                fileId
        )).isTrue();
        mockMvc.perform(get(URI + "/" + fileId)
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isOk());
    }

    @Test
    void concurrentDeleteCallsStorageOnlyOnceAndOneCallerGetsNotFound() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID fileId = insertPosting(owner, "FILE", "READY", "owner/concurrent.pdf", null);
        CountDownLatch start = new CountDownLatch(1);
        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            List<Future<Throwable>> futures = new ArrayList<>();
            for (int index = 0; index < 2; index++) {
                futures.add(executor.submit(() -> {
                    start.await(5, TimeUnit.SECONDS);
                    try {
                        service.delete(jwtToken(owner), fileId);
                        return null;
                    } catch (Throwable failure) {
                        return failure;
                    }
                }));
            }
            start.countDown();
            List<Throwable> failures = new ArrayList<>();
            for (Future<Throwable> future : futures) {
                Throwable failure = future.get(10, TimeUnit.SECONDS);
                if (failure != null) {
                    failures.add(failure);
                }
            }
            assertThat(failures)
                    .singleElement()
                    .isInstanceOf(ResourceNotFoundException.class);
        }

        verify(storage).delete("job-postings", "owner/concurrent.pdf");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT deleted_at IS NOT NULL FROM job_postings WHERE job_posting_id = ?",
                Boolean.class,
                fileId
        )).isTrue();
    }

    @Test
    void deletedAndOtherOwnersResourcesAlwaysReturnNotFound() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID deleted = insertPosting(
                owner,
                "TEXT",
                "READY",
                null,
                OffsetDateTime.now()
        );

        assertNotFound(owner, deleted);
        assertNotFound(other, deleted);
        delete(other, deleted).andExpect(status().isNotFound());
    }

    private org.springframework.test.web.servlet.ResultActions createText(
            UUID userId,
            String inputType,
            String rawText
    ) throws Exception {
        return mockMvc.perform(post(URI)
                .contentType(MediaType.APPLICATION_JSON)
                .content(textBody(inputType, rawText))
                .with(jwt().jwt(token -> token.subject(userId.toString()))));
    }

    private String textBody(String inputType, String rawText) {
        return """
                {"inputType":"%s","rawText":"%s"}
                """.formatted(
                inputType,
                rawText.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n")
        );
    }

    private org.springframework.test.web.servlet.ResultActions upload(
            UUID userId,
            String inputType,
            MockMultipartFile file,
            String rawText
    ) throws Exception {
        var request = multipart(URI)
                .file(file)
                .param("inputType", inputType)
                .with(jwt().jwt(token -> token.subject(userId.toString())));
        if (rawText != null) {
            request.param("rawText", rawText);
        }
        return mockMvc.perform(request);
    }

    private org.springframework.test.web.servlet.ResultActions patch(
            UUID userId,
            UUID id,
            String content
    ) throws Exception {
        return mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                .patch(URI + "/" + id)
                .contentType(MediaType.APPLICATION_JSON)
                .content(content)
                .with(jwt().jwt(token -> token.subject(userId.toString()))));
    }

    private org.springframework.test.web.servlet.ResultActions delete(UUID userId, UUID id)
            throws Exception {
        return mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders
                .delete(URI + "/" + id)
                .with(jwt().jwt(token -> token.subject(userId.toString()))));
    }

    private void assertNotFound(UUID userId, UUID id) throws Exception {
        mockMvc.perform(get(URI + "/" + id)
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("RESOURCE_NOT_FOUND"));
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

    private UUID insertPosting(
            UUID userId,
            String inputType,
            String status,
            String objectKey,
            OffsetDateTime deletedAt
    ) {
        UUID id = UUID.randomUUID();
        if ("FILE".equals(inputType)) {
            jdbcTemplate.update(
                    """
                    INSERT INTO job_postings (
                      job_posting_id, user_id, input_type, original_file_name,
                      storage_bucket, storage_path, mime_type, file_size_bytes,
                      extracted_text, company_name, target_role, main_responsibilities,
                      qualifications, processing_status, processing_error, deleted_at
                    ) VALUES (?, ?, 'FILE', 'posting.pdf', 'job-postings', ?,
                      'application/pdf', 100, 'extracted', 'FaceFit', 'Backend',
                      'API', 'Java', ?, ?, ?)
                    """,
                    id,
                    userId,
                    objectKey,
                    status,
                    "FAILED".equals(status) ? "STRUCTURE_REQUIRED_FIELDS_MISSING" : null,
                    deletedAt
            );
        } else {
            jdbcTemplate.update(
                    """
                    INSERT INTO job_postings (
                      job_posting_id, user_id, input_type, raw_text,
                      company_name, target_role, main_responsibilities,
                      qualifications, processing_status, processing_error, deleted_at
                    ) VALUES (?, ?, 'TEXT', '회사명: FaceFit', 'FaceFit', 'Backend',
                      'API', 'Java', ?, ?, ?)
                    """,
                    id,
                    userId,
                    status,
                    "FAILED".equals(status) ? "STRUCTURE_REQUIRED_FIELDS_MISSING" : null,
                    deletedAt
            );
        }
        return id;
    }

    private long postingCount() {
        return jdbcTemplate.queryForObject("SELECT count(*) FROM job_postings", Long.class);
    }

    private MockMultipartFile pdfFile() throws Exception {
        return new MockMultipartFile("file", "posting.pdf", "application/pdf", validPdf());
    }

    private byte[] validPdf() throws Exception {
        try (PDDocument document = new PDDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.addPage(new PDPage());
            document.save(output);
            return output.toByteArray();
        }
    }

    private byte[] hwp5() throws Exception {
        byte[] header = new byte[256];
        byte[] signature = "HWP Document File".getBytes(StandardCharsets.US_ASCII);
        System.arraycopy(signature, 0, header, 0, signature.length);
        header[35] = 5;
        try (POIFSFileSystem fileSystem = new POIFSFileSystem();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            DirectoryEntry root = fileSystem.getRoot();
            root.createDocument("FileHeader", new ByteArrayInputStream(header));
            root.createDocument("DocInfo", new ByteArrayInputStream(new byte[]{0, 0, 0, 0}));
            DirectoryEntry bodyText = root.createDirectory("BodyText");
            bodyText.createDocument("Section0", new ByteArrayInputStream(new byte[]{0, 0, 0, 0}));
            fileSystem.writeFilesystem(output);
            return output.toByteArray();
        }
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
