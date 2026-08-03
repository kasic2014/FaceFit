package com.facefit.backend.database;

import com.facefit.backend.legal.domain.LegalActionType;
import com.facefit.backend.document.domain.CareerDocument;
import com.facefit.backend.document.domain.CareerDocumentType;
import com.facefit.backend.document.repository.CareerDocumentRepository;
import com.facefit.backend.legal.domain.LegalDocument;
import com.facefit.backend.legal.domain.LegalRecordActionType;
import com.facefit.backend.legal.domain.UserLegalRecord;
import com.facefit.backend.legal.repository.LegalDocumentRepository;
import com.facefit.backend.legal.repository.UserLegalRecordRepository;
import com.facefit.backend.jobposting.domain.JobPosting;
import com.facefit.backend.jobposting.domain.JobPostingInputType;
import com.facefit.backend.jobposting.domain.JobPostingProcessingStatus;
import com.facefit.backend.jobposting.repository.JobPostingRepository;
import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.repository.InterviewSessionRepository;
import com.facefit.backend.member.domain.MemberStatus;
import com.facefit.backend.member.domain.OnboardingStatus;
import com.facefit.backend.member.domain.Profile;
import com.facefit.backend.member.repository.ProfileRepository;
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.net.InetAddress;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@Testcontainers(disabledWithoutDocker = true)
class CoreDatabaseIntegrationTest {

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
    private Flyway flyway;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Autowired
    private EntityManager entityManager;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private ProfileRepository profileRepository;

    @Autowired
    private LegalDocumentRepository legalDocumentRepository;

    @Autowired
    private UserLegalRecordRepository userLegalRecordRepository;

    @Autowired
    private CareerDocumentRepository careerDocumentRepository;

    @Autowired
    private JobPostingRepository jobPostingRepository;

    @Autowired
    private InterviewSessionRepository interviewSessionRepository;

    @MockitoBean
    private JwtDecoder jwtDecoder;

    @BeforeEach
    void clearDatabase() {
        jdbcTemplate.execute(
                "TRUNCATE TABLE interview_sessions, job_postings, career_documents, "
                        + "user_legal_records, "
                        + "legal_documents, profiles, auth.users CASCADE"
        );
        entityManager.clear();
    }

    @Test
    void flywayMigrationsCreateCoreCareerDocumentAndJobPostingTables() {
        assertThat(flyway.info().current().getVersion().getVersion()).isEqualTo("7");
        assertThat(tableExists("profiles")).isTrue();
        assertThat(tableExists("legal_documents")).isTrue();
        assertThat(tableExists("user_legal_records")).isTrue();
        assertThat(tableExists("career_documents")).isTrue();
        assertThat(tableExists("job_postings")).isTrue();
        assertThat(tableExists("interview_sessions")).isTrue();
        assertThat(tableExists("interview_turns")).isTrue();
        assertThat(tableExists("interview_answers")).isTrue();
        assertThat(tableExists("interview_processing_jobs")).isTrue();
        assertThat(tableExists("api_idempotency_records")).isTrue();
        assertThat(tableExists("interview_analysis_results")).isTrue();
        assertThat(tableExists("interview_reports")).isTrue();

        Integer migrationTableCount = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'profiles', 'legal_documents', 'user_legal_records',
                    'career_documents', 'job_postings', 'interview_sessions',
                    'interview_turns', 'interview_answers',
                    'interview_processing_jobs', 'api_idempotency_records',
                    'interview_analysis_results', 'interview_reports'
                  )
                """,
                Integer.class
        );
        assertThat(migrationTableCount).isEqualTo(12);
    }

    @Test
    void applicationContextLoadsAndJpaMetamodelContainsAllEntities() {
        Set<String> entityNames = entityManagerFactory.getMetamodel()
                .getEntities()
                .stream()
                .map(type -> type.getJavaType().getSimpleName())
                .collect(java.util.stream.Collectors.toSet());

        assertThat(entityNames)
                .contains(
                        "Profile",
                        "LegalDocument",
                        "UserLegalRecord",
                        "CareerDocument",
                        "JobPosting",
                        "InterviewSession",
                        "InterviewAnalysisResult",
                        "InterviewReport"
                );
    }

    @Test
    void jobPostingSchemaMatchesFileAndTextEntities() {
        Profile profile = saveProfileWithDatabaseDefaults();
        JobPosting filePosting = jobPostingRepository.saveAndFlush(JobPosting.createFile(
                UUID.randomUUID(),
                profile,
                "posting.hwp",
                "job-postings",
                profile.getUserId() + "/posting.hwp",
                "application/x-hwp-v5",
                512
        ));
        JobPosting textPosting = jobPostingRepository.saveAndFlush(JobPosting.createText(
                UUID.randomUUID(),
                profile,
                "회사명: FaceFit\n지원 직무: 백엔드 개발자"
        ));

        assertThat(filePosting.getInputType()).isEqualTo(JobPostingInputType.FILE);
        assertThat(filePosting.getMimeType()).isEqualTo("application/x-hwp-v5");
        assertThat(filePosting.getProcessingStatus())
                .isEqualTo(JobPostingProcessingStatus.PROCESSING);
        assertThat(textPosting.getInputType()).isEqualTo(JobPostingInputType.TEXT);
        assertThat(textPosting.getStoragePath()).isNull();
        assertThat(textPosting.getCreatedAt()).isNotNull();
        assertThat(textPosting.getUpdatedAt()).isNotNull();
    }

    @Test
    void jobPostingInputPayloadAndProfileForeignKeyConstraintsAreEnforced() {
        Profile profile = saveProfileWithDatabaseDefaults();

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO job_postings (
                    job_posting_id, user_id, input_type, raw_text,
                    storage_bucket, storage_path, mime_type, file_size_bytes
                ) VALUES (?, ?, 'TEXT', 'text', 'job-postings', 'invalid.pdf',
                    'application/pdf', 10)
                """,
                UUID.randomUUID(),
                profile.getUserId()
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO job_postings (
                    job_posting_id, user_id, input_type, raw_text
                ) VALUES (?, ?, 'TEXT', 'text')
                """,
                UUID.randomUUID(),
                UUID.randomUUID()
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO job_postings (
                    job_posting_id, user_id, input_type, raw_text, processing_status
                ) VALUES (?, ?, 'TEXT', 'text', 'WAITING')
                """,
                UUID.randomUUID(),
                profile.getUserId()
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void careerDocumentSchemaMatchesEntityAndDefaults() {
        Profile profile = saveProfileWithDatabaseDefaults();
        CareerDocument saved = careerDocumentRepository.saveAndFlush(CareerDocument.create(
                UUID.randomUUID(),
                profile,
                CareerDocumentType.RESUME,
                "resume.pdf",
                "career-documents",
                profile.getUserId() + "/document/object.pdf",
                "application/pdf",
                128
        ));

        assertThat(saved.getProcessingStatus().name()).isEqualTo("PROCESSING");
        assertThat(saved.getDeletedAt()).isNull();
        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getUpdatedAt()).isNotNull();
    }

    @Test
    void careerDocumentConstraintsAndProfileForeignKeyAreEnforced() {
        UUID missingUser = UUID.randomUUID();
        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO career_documents (
                  document_id, user_id, document_type, original_file_name,
                  storage_bucket, storage_path, mime_type, file_size_bytes
                ) VALUES (?, ?, 'RESUME', 'resume.pdf', 'career-documents', ?, 'application/pdf', 1)
                """,
                UUID.randomUUID(),
                missingUser,
                UUID.randomUUID() + ".pdf"
        )).isInstanceOf(DataIntegrityViolationException.class);

        Profile profile = saveProfileWithDatabaseDefaults();
        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO career_documents (
                  document_id, user_id, document_type, original_file_name,
                  storage_bucket, storage_path, mime_type, file_size_bytes
                ) VALUES (?, ?, 'JOB_POSTING', 'job.pdf', 'career-documents', ?, 'application/pdf', 0)
                """,
                UUID.randomUUID(),
                profile.getUserId(),
                UUID.randomUUID() + ".pdf"
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void profileCanBeSavedForExistingSupabaseAuthUser() {
        UUID userId = insertAuthUser();

        Profile saved = profileRepository.saveAndFlush(Profile.withDatabaseDefaults(userId));

        assertThat(saved.getUserId()).isEqualTo(userId);
        assertThat(profileRepository.findById(userId)).isPresent();
    }

    @Test
    void profileCannotBeSavedForMissingSupabaseAuthUser() {
        UUID missingUserId = UUID.randomUUID();

        assertThatThrownBy(() ->
                profileRepository.saveAndFlush(Profile.withDatabaseDefaults(missingUserId))
        ).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void profileMemberStatusUsesDatabaseDefaultActive() {
        Profile profile = saveProfileWithDatabaseDefaults();

        assertThat(profile.getMemberStatus()).isEqualTo(MemberStatus.ACTIVE);
    }

    @Test
    void profileOnboardingStatusUsesDatabaseDefaultNotStarted() {
        Profile profile = saveProfileWithDatabaseDefaults();

        assertThat(profile.getOnboardingStatus()).isEqualTo(OnboardingStatus.NOT_STARTED);
        assertThat(profile.getOnboardingCompletedAt()).isNull();
    }

    @Test
    void unsupportedMemberStatusIsRejectedByDatabaseCheckConstraint() {
        UUID userId = insertAuthUser();

        assertThatThrownBy(() -> jdbcTemplate.update(
                "INSERT INTO profiles (user_id, member_status) VALUES (?, ?)",
                userId,
                "SUSPENDED"
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void unsupportedOnboardingStatusIsRejectedByDatabaseCheckConstraint() {
        UUID userId = insertAuthUser();

        assertThatThrownBy(() -> jdbcTemplate.update(
                "INSERT INTO profiles (user_id, onboarding_status) VALUES (?, ?)",
                userId,
                "SKIPPED"
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void completedOnboardingRequiresCompletionTimestamp() {
        UUID userId = insertAuthUser();

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO profiles (
                    user_id,
                    onboarding_status,
                    onboarding_completed_at
                ) VALUES (?, 'COMPLETED', NULL)
                """,
                userId
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void requiredColumnsRejectNullValues() {
        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO legal_documents (
                    document_type,
                    legal_action_type,
                    title,
                    version,
                    content,
                    effective_at
                ) VALUES (?, ?, NULL, ?, ?, ?)
                """,
                "TERMS",
                "CONSENT",
                "1.0",
                "terms",
                OffsetDateTime.now()
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void unsupportedLegalActionTypeIsRejectedByDatabaseCheckConstraint() {
        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO legal_documents (
                    document_type,
                    legal_action_type,
                    title,
                    version,
                    content,
                    effective_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                "TERMS",
                "SIGNATURE",
                "Terms",
                "1.0",
                "terms",
                OffsetDateTime.now()
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void legalDocumentUniqueConstraintsAreEnforced() {
        saveLegalDocument("TERMS", "1.0", false, true, OffsetDateTime.now().minusDays(1));

        assertThatThrownBy(() ->
                saveLegalDocument("TERMS", "1.0", false, false, OffsetDateTime.now())
        ).isInstanceOf(DataIntegrityViolationException.class);

        saveLegalDocument("PRIVACY", "1.0", true, true, OffsetDateTime.now().minusDays(1));

        assertThatThrownBy(() ->
                saveLegalDocument("PRIVACY", "2.0", true, true, OffsetDateTime.now())
        ).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void legalDocumentAndUserLegalRecordConstraintsAreEnforced() throws Exception {
        Profile profile = saveProfileWithDatabaseDefaults();
        LegalDocument legalDocument = saveLegalDocument(
                "TERMS",
                "1.0",
                true,
                true,
                OffsetDateTime.now().minusDays(1)
        );

        UserLegalRecord record = userLegalRecordRepository.saveAndFlush(
                UserLegalRecord.create(
                        profile,
                        legalDocument,
                        LegalRecordActionType.CONSENTED,
                        null,
                        InetAddress.getByName("127.0.0.1"),
                        "integration-test"
                )
        );
        assertThat(record.getLegalRecordId()).isNotNull();
        entityManager.clear();
        UserLegalRecord reloadedRecord = userLegalRecordRepository
                .findById(record.getLegalRecordId())
                .orElseThrow();
        assertThat(reloadedRecord.getCollectionMethod()).isEqualTo("WEB_CHECKBOX");

        assertThatThrownBy(() -> jdbcTemplate.update(
                "DELETE FROM legal_documents WHERE legal_document_id = ?",
                legalDocument.getLegalDocumentId()
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO user_legal_records (
                    user_id,
                    legal_document_id,
                    action_type
                ) VALUES (?, ?, 'CONSENTED')
                """,
                profile.getUserId(),
                UUID.randomUUID()
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertThatThrownBy(() -> jdbcTemplate.update(
                """
                INSERT INTO user_legal_records (
                    user_id,
                    legal_document_id,
                    action_type
                ) VALUES (?, ?, 'INVALID')
                """,
                profile.getUserId(),
                legalDocument.getLegalDocumentId()
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @Test
    void legalDocumentRepositoryFindsOnlyCurrentlyApplicableRequiredDocuments() {
        LegalDocument requiredCurrent = saveLegalDocument(
                "TERMS",
                "1.0",
                true,
                true,
                OffsetDateTime.now().minusDays(1)
        );
        saveLegalDocument(
                "PRIVACY",
                "1.0",
                false,
                true,
                OffsetDateTime.now().minusDays(1)
        );
        saveLegalDocument(
                "MARKETING",
                "1.0",
                true,
                false,
                OffsetDateTime.now().minusDays(1)
        );
        saveLegalDocument(
                "FUTURE_TERMS",
                "1.0",
                true,
                true,
                OffsetDateTime.now().plusDays(1)
        );

        List<LegalDocument> result = legalDocumentRepository
                .findAllByIsOnboardingRequiredTrueAndIsCurrentTrueAndEffectiveAtLessThanEqualOrderByDocumentTypeAsc(
                        OffsetDateTime.now()
                );

        assertThat(result)
                .extracting(LegalDocument::getLegalDocumentId)
                .containsExactly(requiredCurrent.getLegalDocumentId());
    }

    @Test
    void userLegalRecordRepositoryFindsHistoryAndDetectsDuplicateAction() {
        Profile profile = saveProfileWithDatabaseDefaults();
        LegalDocument legalDocument = saveLegalDocument(
                "TERMS",
                "1.0",
                true,
                true,
                OffsetDateTime.now().minusDays(1)
        );

        UserLegalRecord consented = userLegalRecordRepository.saveAndFlush(
                UserLegalRecord.create(
                        profile,
                        legalDocument,
                        LegalRecordActionType.CONSENTED,
                        "WEB_CHECKBOX",
                        null,
                        null
                )
        );
        UserLegalRecord withdrawn = userLegalRecordRepository.saveAndFlush(
                UserLegalRecord.create(
                        profile,
                        legalDocument,
                        LegalRecordActionType.WITHDRAWN,
                        "WEB_CHECKBOX",
                        null,
                        null
                )
        );
        jdbcTemplate.update(
                "UPDATE user_legal_records SET recorded_at = ? WHERE legal_record_id = ?",
                OffsetDateTime.now().minusMinutes(2),
                consented.getLegalRecordId()
        );
        jdbcTemplate.update(
                "UPDATE user_legal_records SET recorded_at = ? WHERE legal_record_id = ?",
                OffsetDateTime.now().minusMinutes(1),
                withdrawn.getLegalRecordId()
        );
        entityManager.clear();

        List<UserLegalRecord> history = userLegalRecordRepository
                .findAllByProfile_UserIdAndLegalDocument_LegalDocumentIdOrderByRecordedAtDesc(
                        profile.getUserId(),
                        legalDocument.getLegalDocumentId()
                );

        assertThat(history)
                .extracting(UserLegalRecord::getActionType)
                .containsExactly(
                        LegalRecordActionType.WITHDRAWN,
                        LegalRecordActionType.CONSENTED
                );
        assertThat(userLegalRecordRepository
                .existsByProfile_UserIdAndLegalDocument_LegalDocumentIdAndActionType(
                        profile.getUserId(),
                        legalDocument.getLegalDocumentId(),
                        LegalRecordActionType.CONSENTED
                )).isTrue();
    }

    private boolean tableExists(String tableName) {
        return Boolean.TRUE.equals(jdbcTemplate.queryForObject(
                "SELECT to_regclass('public.' || ?) IS NOT NULL",
                Boolean.class,
                tableName
        ));
    }

    private UUID insertAuthUser() {
        UUID userId = UUID.randomUUID();
        jdbcTemplate.update("INSERT INTO auth.users (id) VALUES (?)", userId);
        return userId;
    }

    private Profile saveProfileWithDatabaseDefaults() {
        UUID userId = insertAuthUser();
        profileRepository.saveAndFlush(Profile.withDatabaseDefaults(userId));
        entityManager.clear();
        return profileRepository.findById(userId).orElseThrow();
    }

    private LegalDocument saveLegalDocument(
            String documentType,
            String version,
            boolean onboardingRequired,
            boolean current,
            OffsetDateTime effectiveAt
    ) {
        LegalDocument legalDocument = LegalDocument.create(
                documentType,
                LegalActionType.CONSENT,
                documentType + " title",
                version,
                documentType + " content",
                onboardingRequired,
                current,
                effectiveAt
        );
        return legalDocumentRepository.saveAndFlush(legalDocument);
    }
}
