package com.facefit.backend.interview.domain;

import com.facefit.backend.document.domain.CareerDocument;
import com.facefit.backend.jobposting.domain.JobPosting;
import com.facefit.backend.member.domain.Profile;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.ColumnDefault;

import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;

@Getter
@Entity
@Table(name = "interview_sessions")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewSession {

    @Id
    @Column(name = "session_id", nullable = false, updatable = false)
    private UUID sessionId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, updatable = false)
    private Profile profile;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "resume_document_id", nullable = false)
    private CareerDocument resumeDocument;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "cover_letter_document_id")
    private CareerDocument coverLetterDocument;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "job_posting_id", nullable = false)
    private JobPosting jobPosting;

    @Column(name = "persona", nullable = false, length = 50)
    private String persona;

    @Column(name = "difficulty", nullable = false, length = 30)
    private String difficulty;

    @Enumerated(EnumType.STRING)
    @ColumnDefault("'DRAFT'")
    @Column(name = "session_status", nullable = false, length = 30)
    private InterviewSessionStatus status;

    @Column(name = "snapshot_company_name", nullable = false, columnDefinition = "TEXT")
    private String companyName;

    @Column(name = "snapshot_target_role", nullable = false, columnDefinition = "TEXT")
    private String targetRole;

    @Column(
            name = "snapshot_main_responsibilities",
            nullable = false,
            columnDefinition = "TEXT"
    )
    private String mainResponsibilities;

    @Column(name = "snapshot_qualifications", nullable = false, columnDefinition = "TEXT")
    private String qualifications;

    @Column(name = "snapshot_preferred_qualifications", columnDefinition = "TEXT")
    private String preferredQualifications;

    @Column(name = "snapshot_technologies_tools", columnDefinition = "TEXT")
    private String technologiesTools;

    @Column(name = "snapshot_core_competencies", columnDefinition = "TEXT")
    private String coreCompetencies;

    @Column(name = "snapshot_company_business_intro", columnDefinition = "TEXT")
    private String companyBusinessIntro;

    @Column(name = "current_question_order")
    private Integer currentQuestionOrder;

    @ColumnDefault("false")
    @Column(name = "voice_analysis_enabled", nullable = false, updatable = false)
    private boolean voiceAnalysisEnabled;

    @Enumerated(EnumType.STRING)
    @Column(name = "completion_type", length = 30)
    private InterviewCompletionType completionType;

    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    @Column(name = "started_at")
    private OffsetDateTime startedAt;

    @Column(name = "interview_completed_at")
    private OffsetDateTime interviewCompletedAt;

    @Column(name = "analysis_started_at")
    private OffsetDateTime analysisStartedAt;

    @Column(name = "completed_at")
    private OffsetDateTime completedAt;

    @Column(name = "interrupted_at")
    private OffsetDateTime interruptedAt;

    @Version
    @ColumnDefault("0")
    @Column(name = "row_version", nullable = false)
    private long rowVersion;

    private InterviewSession(
            UUID sessionId,
            Profile profile,
            CareerDocument resumeDocument,
            CareerDocument coverLetterDocument,
            JobPosting jobPosting,
            String persona,
            String difficulty,
            JobPostingSnapshot snapshot
    ) {
        this.sessionId = Objects.requireNonNull(sessionId);
        this.profile = Objects.requireNonNull(profile);
        this.resumeDocument = Objects.requireNonNull(resumeDocument);
        this.coverLetterDocument = coverLetterDocument;
        this.jobPosting = Objects.requireNonNull(jobPosting);
        this.persona = Objects.requireNonNull(persona);
        this.difficulty = Objects.requireNonNull(difficulty);
        this.status = InterviewSessionStatus.DRAFT;
        this.voiceAnalysisEnabled = profile.isVoiceAnalysisConsented();
        applySnapshot(Objects.requireNonNull(snapshot));
    }

    public static InterviewSession create(
            UUID sessionId,
            Profile profile,
            CareerDocument resumeDocument,
            CareerDocument coverLetterDocument,
            JobPosting jobPosting,
            String persona,
            String difficulty,
            JobPostingSnapshot snapshot
    ) {
        return new InterviewSession(
                sessionId,
                profile,
                resumeDocument,
                coverLetterDocument,
                jobPosting,
                persona,
                difficulty,
                snapshot
        );
    }

    public void changeResumeDocument(CareerDocument resumeDocument) {
        this.resumeDocument = Objects.requireNonNull(resumeDocument);
    }

    public void changeCoverLetterDocument(CareerDocument coverLetterDocument) {
        this.coverLetterDocument = coverLetterDocument;
    }

    public void changeJobPosting(
            JobPosting jobPosting,
            JobPostingSnapshot snapshot
    ) {
        this.jobPosting = Objects.requireNonNull(jobPosting);
        applySnapshot(Objects.requireNonNull(snapshot));
    }

    public void changePersona(String persona) {
        this.persona = Objects.requireNonNull(persona);
    }

    public void changeDifficulty(String difficulty) {
        this.difficulty = Objects.requireNonNull(difficulty);
    }

    public void startAfterQuestionsGenerated(OffsetDateTime startedAt) {
        if (status != InterviewSessionStatus.DRAFT) {
            throw new IllegalStateException("DRAFT 세션만 시작할 수 있습니다.");
        }
        status = InterviewSessionStatus.IN_PROGRESS;
        this.startedAt = Objects.requireNonNull(startedAt);
        currentQuestionOrder = 1;
    }

    public void moveCurrentQuestionOrder(Integer questionOrder) {
        if (status != InterviewSessionStatus.IN_PROGRESS) {
            throw new IllegalStateException("진행 중인 세션의 질문만 변경할 수 있습니다.");
        }
        currentQuestionOrder = questionOrder;
    }

    public void completeInterview(OffsetDateTime completedAt) {
        if (status != InterviewSessionStatus.IN_PROGRESS) {
            throw new IllegalStateException("진행 중인 세션만 종료할 수 있습니다.");
        }
        status = InterviewSessionStatus.INTERVIEW_COMPLETED;
        completionType = InterviewCompletionType.NORMAL;
        interviewCompletedAt = Objects.requireNonNull(completedAt);
        currentQuestionOrder = null;
    }

    public void interruptInterview(OffsetDateTime interruptedAt) {
        if (status != InterviewSessionStatus.IN_PROGRESS) {
            throw new IllegalStateException("진행 중인 세션만 중단할 수 있습니다.");
        }
        status = InterviewSessionStatus.INTERRUPTED;
        completionType = InterviewCompletionType.USER_INTERRUPTED;
        this.interruptedAt = Objects.requireNonNull(interruptedAt);
        currentQuestionOrder = null;
    }

    public void beginAnalysis(OffsetDateTime startedAt) {
        if (status != InterviewSessionStatus.INTERVIEW_COMPLETED
                || completionType != InterviewCompletionType.NORMAL) {
            throw new IllegalStateException("정상 종료 세션만 분석할 수 있습니다.");
        }
        status = InterviewSessionStatus.ANALYZING;
        if (analysisStartedAt == null) {
            analysisStartedAt = Objects.requireNonNull(startedAt);
        }
    }

    public void completeAnalysis(OffsetDateTime completedAt) {
        if (status != InterviewSessionStatus.ANALYZING
                || completionType != InterviewCompletionType.NORMAL) {
            throw new IllegalStateException("분석 중인 정상 종료 세션만 완료할 수 있습니다.");
        }
        status = InterviewSessionStatus.COMPLETED;
        if (this.completedAt == null) {
            this.completedAt = Objects.requireNonNull(completedAt);
        }
    }

    private void applySnapshot(JobPostingSnapshot snapshot) {
        this.companyName = Objects.requireNonNull(snapshot.companyName());
        this.targetRole = Objects.requireNonNull(snapshot.targetRole());
        this.mainResponsibilities = Objects.requireNonNull(snapshot.mainResponsibilities());
        this.qualifications = Objects.requireNonNull(snapshot.qualifications());
        this.preferredQualifications = snapshot.preferredQualifications();
        this.technologiesTools = snapshot.technologiesTools();
        this.coreCompetencies = snapshot.coreCompetencies();
        this.companyBusinessIntro = snapshot.companyBusinessIntro();
    }

    @PrePersist
    void initializeTimestamps() {
        OffsetDateTime now = OffsetDateTime.now();
        if (createdAt == null) {
            createdAt = now;
        }
        if (updatedAt == null) {
            updatedAt = now;
        }
    }

    @PreUpdate
    void updateTimestamp() {
        updatedAt = OffsetDateTime.now();
    }
}
