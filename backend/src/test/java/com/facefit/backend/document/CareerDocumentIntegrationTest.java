package com.facefit.backend.document;

import com.facefit.backend.common.exception.ResourceNotFoundException;
import com.facefit.backend.common.exception.StorageOperationException;
import com.facefit.backend.document.application.CareerDocumentObjectKeyFactory;
import com.facefit.backend.document.application.CareerDocumentService;
import com.facefit.backend.document.storage.CareerDocumentStorage;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.encryption.AccessPermission;
import org.apache.pdfbox.pdmodel.encryption.StandardProtectionPolicy;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
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

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
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
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
class CareerDocumentIntegrationTest {

    private static final String URI = "/api/v1/career-documents";
    private static final String PDF_MIME = "application/pdf";
    private static final String DOCX_MIME =
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

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
                "facefit.storage.supabase.career-documents-bucket",
                () -> "career-documents"
        );
    }

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private CareerDocumentService service;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @MockitoBean
    private CareerDocumentStorage storage;

    @MockitoBean
    private CareerDocumentObjectKeyFactory objectKeyFactory;

    @BeforeEach
    void clearDatabase() {
        jdbcTemplate.execute(
                "TRUNCATE TABLE career_documents, user_legal_records, legal_documents, profiles, auth.users CASCADE"
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
    void uploadRequiresAuthentication() throws Exception {
        mockMvc.perform(multipart(URI)
                        .file(pdfFile("resume.pdf"))
                        .param("documentType", "RESUME"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void inactiveAndIncompleteMembersCannotUpload() throws Exception {
        UUID blocked = insertProfile("BLOCKED", "COMPLETED");
        UUID incomplete = insertProfile("ACTIVE", "NOT_STARTED");

        upload(blocked, "RESUME", pdfFile("resume.pdf"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("MEMBER_ACCESS_DENIED"));
        upload(incomplete, "RESUME", pdfFile("resume.pdf"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.error.code").value("ONBOARDING_REQUIRED"));
        assertThat(documentCount()).isZero();
    }

    @Test
    void validPdfResumeUploadStoresPrivateMetadata() throws Exception {
        UUID userId = insertCompletedProfile();

        upload(userId, "RESUME", pdfFile("../../resume.pdf"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.documentType").value("RESUME"))
                .andExpect(jsonPath("$.data.status").value("PROCESSING"))
                .andExpect(jsonPath("$.data.storageBucket").doesNotExist())
                .andExpect(jsonPath("$.data.storagePath").doesNotExist());

        assertThat(documentCount()).isOne();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT original_file_name FROM career_documents",
                String.class
        )).isEqualTo("resume.pdf");
        String objectKey = jdbcTemplate.queryForObject(
                "SELECT storage_path FROM career_documents",
                String.class
        );
        assertThat(objectKey).startsWith(userId + "/").endsWith(".pdf");
        verify(storage).upload(
                eq("career-documents"),
                eq(objectKey),
                eq(PDF_MIME),
                any(byte[].class)
        );
    }

    @Test
    void validDocxCoverLetterUploadSucceeds() throws Exception {
        UUID userId = insertCompletedProfile();

        upload(userId, "COVER_LETTER", docxFile("cover.docx", false))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.documentType").value("COVER_LETTER"))
                .andExpect(jsonPath("$.data.status").value("PROCESSING"));

        assertThat(jdbcTemplate.queryForObject(
                "SELECT mime_type FROM career_documents",
                String.class
        )).isEqualTo(DOCX_MIME);
    }

    @Test
    void invalidDocumentTypeMissingAndEmptyFilesAreRejected() throws Exception {
        UUID userId = insertCompletedProfile();

        upload(userId, "JOB_POSTING", pdfFile("resume.pdf"))
                .andExpect(status().isBadRequest());
        mockMvc.perform(multipart(URI)
                        .param("documentType", "RESUME")
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isBadRequest());
        upload(userId, "RESUME", new MockMultipartFile(
                "file",
                "empty.pdf",
                PDF_MIME,
                new byte[0]
        )).andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_DOCUMENT_FILE"));
        assertThat(documentCount()).isZero();
    }

    @Test
    void extensionMimeSignatureAndSizeMismatchesAreRejected() throws Exception {
        UUID userId = insertCompletedProfile();
        List<MockMultipartFile> invalid = List.of(
                new MockMultipartFile("file", "resume.txt", "text/plain", "text".getBytes()),
                new MockMultipartFile("file", "resume.pdf", "text/plain", validPdf()),
                new MockMultipartFile("file", "resume.pdf", PDF_MIME, "not pdf".getBytes()),
                new MockMultipartFile("file", "resume.docx", DOCX_MIME, "PK fake".getBytes()),
                new MockMultipartFile(
                        "file",
                        "large.pdf",
                        PDF_MIME,
                        new byte[10 * 1024 * 1024 + 1]
                )
        );
        for (MockMultipartFile file : invalid) {
            upload(userId, "RESUME", file)
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.error.code").value("INVALID_DOCUMENT_FILE"));
        }
        assertThat(documentCount()).isZero();
    }

    @Test
    void encryptedPdfPasswordDocxDocmAndMacroDocxAreRejected() throws Exception {
        UUID userId = insertCompletedProfile();
        List<MockMultipartFile> invalid = List.of(
                new MockMultipartFile("file", "secret.pdf", PDF_MIME, encryptedPdf()),
                new MockMultipartFile(
                        "file",
                        "secret.docx",
                        DOCX_MIME,
                        new byte[]{(byte) 0xD0, (byte) 0xCF, 0x11, (byte) 0xE0}
                ),
                new MockMultipartFile("file", "macro.docm", DOCX_MIME, docxBytes(false)),
                docxFile("macro.docx", true)
        );
        for (MockMultipartFile file : invalid) {
            upload(userId, "RESUME", file)
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.error.code").value("INVALID_DOCUMENT_FILE"));
        }
        assertThat(documentCount()).isZero();
    }

    @Test
    void storageUploadFailureLeavesNoDatabaseRow() throws Exception {
        UUID userId = insertCompletedProfile();
        doThrow(new StorageOperationException("upload failed"))
                .when(storage).upload(anyString(), anyString(), anyString(), any(byte[].class));

        upload(userId, "RESUME", pdfFile("resume.pdf"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.error.code").value("STORAGE_OPERATION_FAILED"));

        assertThat(documentCount()).isZero();
    }

    @Test
    void databaseFailureDeletesUploadedObjectAsCompensation() throws Exception {
        UUID userId = insertCompletedProfile();
        String duplicateKey = userId + "/existing/fixed.pdf";
        insertDocument(userId, "RESUME", "PROCESSING", duplicateKey, null);
        when(objectKeyFactory.create(any(), any(), anyString())).thenReturn(duplicateKey);

        upload(userId, "RESUME", pdfFile("resume.pdf"))
                .andExpect(status().isInternalServerError());

        verify(storage).upload(
                eq("career-documents"),
                eq(duplicateKey),
                eq(PDF_MIME),
                any(byte[].class)
        );
        verify(storage).delete("career-documents", duplicateKey);
        assertThat(documentCount()).isOne();
    }

    @Test
    void listReturnsOnlyOwnedActiveDocumentsWithFiltersAndStableOrder() throws Exception {
        UUID userId = insertCompletedProfile();
        UUID otherUser = insertCompletedProfile();
        UUID older = insertDocument(userId, "RESUME", "READY", "older.pdf", null);
        UUID newer = insertDocument(userId, "COVER_LETTER", "PROCESSING", "newer.docx", null);
        insertDocument(userId, "RESUME", "FAILED", "deleted.pdf", OffsetDateTime.now());
        insertDocument(otherUser, "RESUME", "READY", "other.pdf", null);
        jdbcTemplate.update(
                "UPDATE career_documents SET created_at = ? WHERE document_id = ?",
                OffsetDateTime.now().minusDays(1),
                older
        );
        jdbcTemplate.update(
                "UPDATE career_documents SET created_at = ? WHERE document_id = ?",
                OffsetDateTime.now(),
                newer
        );

        mockMvc.perform(get(URI)
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.content.length()").value(2))
                .andExpect(jsonPath("$.data.content[0].documentId").value(newer.toString()))
                .andExpect(jsonPath("$.data.content[1].documentId").value(older.toString()))
                .andExpect(jsonPath("$.data.page").value(0))
                .andExpect(jsonPath("$.data.size").value(20))
                .andExpect(jsonPath("$.data.totalElements").value(2))
                .andExpect(jsonPath("$.data.content[0].storagePath").doesNotExist())
                .andExpect(jsonPath("$.data.content[0].deletedAt").doesNotExist());

        mockMvc.perform(get(URI)
                        .param("documentType", "RESUME")
                        .param("status", "READY")
                        .param("page", "0")
                        .param("size", "1")
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.content.length()").value(1))
                .andExpect(jsonPath("$.data.content[0].documentId").value(older.toString()));
    }

    @Test
    void listRejectsInvalidFiltersAndPageRanges() throws Exception {
        UUID userId = insertCompletedProfile();
        for (String uri : List.of(
                URI + "?documentType=JOB_POSTING",
                URI + "?status=QUEUED",
                URI + "?page=-1",
                URI + "?size=0",
                URI + "?size=101"
        )) {
            mockMvc.perform(get(uri)
                            .with(jwt().jwt(token -> token.subject(userId.toString()))))
                    .andExpect(status().isBadRequest());
        }
    }

    @Test
    void detailProtectsOwnershipDeletionAndInternalStorageFields() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID active = insertDocument(owner, "RESUME", "PROCESSING", "active.pdf", null);
        UUID deleted = insertDocument(owner, "RESUME", "FAILED", "deleted.pdf", OffsetDateTime.now());

        mockMvc.perform(get(URI + "/" + active)
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.documentId").value(active.toString()))
                .andExpect(jsonPath("$.data.originalFileName").value("resume.pdf"))
                .andExpect(jsonPath("$.data.storageBucket").doesNotExist())
                .andExpect(jsonPath("$.data.storagePath").doesNotExist())
                .andExpect(jsonPath("$.data.extractedText").doesNotExist());

        for (UUID id : List.of(UUID.randomUUID(), deleted)) {
            assertNotFound(owner, id);
        }
        assertNotFound(other, active);
    }

    @Test
    void deleteSoftDeletesDatabaseAndPermanentlyDeletesStorageObject() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID documentId = insertDocument(owner, "RESUME", "PROCESSING", "object.pdf", null);

        mockMvc.perform(delete(URI + "/" + documentId)
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isNoContent());

        assertThat(jdbcTemplate.queryForObject(
                "SELECT deleted_at IS NOT NULL FROM career_documents WHERE document_id = ?",
                Boolean.class,
                documentId
        )).isTrue();
        verify(storage).delete("career-documents", "object.pdf");
        assertNotFound(owner, documentId);
    }

    @Test
    void deleteReturnsNotFoundForMissingOtherAndAlreadyDeletedDocuments() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID other = insertCompletedProfile();
        UUID active = insertDocument(owner, "RESUME", "PROCESSING", "active.pdf", null);
        UUID deleted = insertDocument(owner, "RESUME", "FAILED", "deleted.pdf", OffsetDateTime.now());

        for (UUID id : List.of(UUID.randomUUID(), deleted)) {
            deleteExpectNotFound(owner, id);
        }
        deleteExpectNotFound(other, active);
    }

    @Test
    void storageDeleteFailureRestoresSoftDelete() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID documentId = insertDocument(owner, "RESUME", "PROCESSING", "object.pdf", null);
        doThrow(new StorageOperationException("delete failed"))
                .when(storage).delete("career-documents", "object.pdf");

        mockMvc.perform(delete(URI + "/" + documentId)
                        .with(jwt().jwt(token -> token.subject(owner.toString()))))
                .andExpect(status().isBadGateway());

        assertThat(jdbcTemplate.queryForObject(
                "SELECT deleted_at IS NULL FROM career_documents WHERE document_id = ?",
                Boolean.class,
                documentId
        )).isTrue();
    }

    @Test
    void concurrentDeleteCallsStorageExactlyOnceAndKeepsConsistentState() throws Exception {
        UUID owner = insertCompletedProfile();
        UUID documentId = insertDocument(owner, "RESUME", "PROCESSING", "object.pdf", null);
        Jwt token = verifiedJwt(owner);
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Throwable>> results = new ArrayList<>();
        try {
            for (int index = 0; index < 2; index++) {
                results.add(executor.submit(() -> {
                    ready.countDown();
                    start.await(10, TimeUnit.SECONDS);
                    try {
                        service.delete(token, documentId);
                        return null;
                    } catch (Throwable throwable) {
                        return throwable;
                    }
                }));
            }
            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
            start.countDown();
            List<Throwable> failures = new ArrayList<>();
            for (Future<Throwable> result : results) {
                Throwable failure = result.get(20, TimeUnit.SECONDS);
                if (failure != null) {
                    failures.add(failure);
                }
            }
            assertThat(failures).hasSize(1);
            assertThat(failures.getFirst()).isInstanceOf(ResourceNotFoundException.class);
        } finally {
            executor.shutdownNow();
        }
        verify(storage).delete("career-documents", "object.pdf");
        assertThat(jdbcTemplate.queryForObject(
                "SELECT deleted_at IS NOT NULL FROM career_documents WHERE document_id = ?",
                Boolean.class,
                documentId
        )).isTrue();
    }

    private org.springframework.test.web.servlet.ResultActions upload(
            UUID userId,
            String documentType,
            MockMultipartFile file
    ) throws Exception {
        return mockMvc.perform(multipart(URI)
                .file(file)
                .param("documentType", documentType)
                .with(jwt().jwt(token -> token.subject(userId.toString()))));
    }

    private void assertNotFound(UUID userId, UUID documentId) throws Exception {
        mockMvc.perform(get(URI + "/" + documentId)
                        .with(jwt().jwt(token -> token.subject(userId.toString()))))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("RESOURCE_NOT_FOUND"));
    }

    private void deleteExpectNotFound(UUID userId, UUID documentId) throws Exception {
        mockMvc.perform(delete(URI + "/" + documentId)
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

    private UUID insertDocument(
            UUID userId,
            String type,
            String status,
            String objectKey,
            OffsetDateTime deletedAt
    ) {
        UUID id = UUID.randomUUID();
        jdbcTemplate.update(
                """
                INSERT INTO career_documents (
                  document_id, user_id, document_type, original_file_name,
                  storage_bucket, storage_path, mime_type, file_size_bytes,
                  processing_status, deleted_at
                ) VALUES (?, ?, ?, 'resume.pdf', 'career-documents', ?, 'application/pdf', 100, ?, ?)
                """,
                id,
                userId,
                type,
                objectKey,
                status,
                deletedAt
        );
        return id;
    }

    private long documentCount() {
        return jdbcTemplate.queryForObject("SELECT count(*) FROM career_documents", Long.class);
    }

    private MockMultipartFile pdfFile(String name) throws Exception {
        return new MockMultipartFile("file", name, PDF_MIME, validPdf());
    }

    private MockMultipartFile docxFile(String name, boolean macro) throws Exception {
        return new MockMultipartFile("file", name, DOCX_MIME, docxBytes(macro));
    }

    private byte[] validPdf() throws Exception {
        try (PDDocument document = new PDDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.addPage(new PDPage());
            document.save(output);
            return output.toByteArray();
        }
    }

    private byte[] encryptedPdf() throws Exception {
        try (PDDocument document = new PDDocument();
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            document.addPage(new PDPage());
            StandardProtectionPolicy policy = new StandardProtectionPolicy(
                    "owner-password",
                    "user-password",
                    new AccessPermission()
            );
            policy.setEncryptionKeyLength(128);
            document.protect(policy);
            document.save(output);
            return output.toByteArray();
        }
    }

    private byte[] docxBytes(boolean macro) throws Exception {
        try (ByteArrayOutputStream output = new ByteArrayOutputStream();
             ZipOutputStream zip = new ZipOutputStream(output)) {
            addZipEntry(zip, "[Content_Types].xml", """
                    <?xml version="1.0" encoding="UTF-8"?>
                    <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                      <Override PartName="/word/document.xml"
                        ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
                    </Types>
                    """);
            addZipEntry(zip, "_rels/.rels", """
                    <?xml version="1.0" encoding="UTF-8"?>
                    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
                      <Relationship Id="rId1"
                        Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
                        Target="word/document.xml"/>
                    </Relationships>
                    """);
            addZipEntry(zip, "word/document.xml", """
                    <?xml version="1.0" encoding="UTF-8"?>
                    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                      <w:body><w:p/></w:body>
                    </w:document>
                    """);
            if (macro) {
                addZipEntry(zip, "word/vbaProject.bin", "macro");
            }
            zip.finish();
            return output.toByteArray();
        }
    }

    private void addZipEntry(ZipOutputStream zip, String name, String content) throws Exception {
        zip.putNextEntry(new ZipEntry(name));
        zip.write(content.getBytes(StandardCharsets.UTF_8));
        zip.closeEntry();
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
}
