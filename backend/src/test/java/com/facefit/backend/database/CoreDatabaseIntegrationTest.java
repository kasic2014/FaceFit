package com.facefit.backend.database;

import com.facefit.backend.legal.domain.LegalActionType;
import com.facefit.backend.legal.domain.LegalDocument;
import com.facefit.backend.legal.domain.LegalRecordActionType;
import com.facefit.backend.legal.domain.UserLegalRecord;
import com.facefit.backend.legal.repository.LegalDocumentRepository;
import com.facefit.backend.legal.repository.UserLegalRecordRepository;
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
    void flywayMigrationCreatesOnlyTheThreeRequestedTables() {
        assertThat(flyway.info().current().getVersion().getVersion()).isEqualTo("1");
        assertThat(tableExists("profiles")).isTrue();
        assertThat(tableExists("legal_documents")).isTrue();
        assertThat(tableExists("user_legal_records")).isTrue();

        Integer migrationTableCount = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('profiles', 'legal_documents', 'user_legal_records')
                """,
                Integer.class
        );
        assertThat(migrationTableCount).isEqualTo(3);
    }

    @Test
    void applicationContextLoadsAndJpaMetamodelContainsTheThreeEntities() {
        Set<String> entityNames = entityManagerFactory.getMetamodel()
                .getEntities()
                .stream()
                .map(type -> type.getJavaType().getSimpleName())
                .collect(java.util.stream.Collectors.toSet());

        assertThat(entityNames)
                .contains("Profile", "LegalDocument", "UserLegalRecord");
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
