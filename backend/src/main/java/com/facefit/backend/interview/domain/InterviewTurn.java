package com.facefit.backend.interview.domain;

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
@Table(name = "interview_turns")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InterviewTurn {

    @Id
    @Column(name = "turn_id", nullable = false, updatable = false)
    private UUID turnId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "session_id", nullable = false, updatable = false)
    private InterviewSession session;

    @Column(name = "generation_job_id", nullable = false, updatable = false)
    private UUID generationJobId;

    @Column(name = "question_order", nullable = false, updatable = false)
    private int questionOrder;

    @Enumerated(EnumType.STRING)
    @Column(name = "question_type", nullable = false, length = 30, updatable = false)
    private InterviewQuestionType questionType;

    @Column(name = "question_category", nullable = false, length = 100, updatable = false)
    private String questionCategory;

    @Column(name = "question_text", nullable = false, length = 500, updatable = false)
    private String questionText;

    @ColumnDefault("true")
    @Column(name = "required", nullable = false, updatable = false)
    private boolean required;

    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false)
    private OffsetDateTime updatedAt;

    @Version
    @ColumnDefault("0")
    @Column(name = "row_version", nullable = false)
    private long rowVersion;

    private InterviewTurn(
            UUID turnId,
            InterviewSession session,
            UUID generationJobId,
            int questionOrder,
            InterviewQuestionType questionType,
            String questionCategory,
            String questionText
    ) {
        this.turnId = Objects.requireNonNull(turnId);
        this.session = Objects.requireNonNull(session);
        this.generationJobId = Objects.requireNonNull(generationJobId);
        this.questionOrder = questionOrder;
        this.questionType = Objects.requireNonNull(questionType);
        this.questionCategory = Objects.requireNonNull(questionCategory);
        this.questionText = Objects.requireNonNull(questionText);
        this.required = true;
    }

    public static InterviewTurn create(
            UUID turnId,
            InterviewSession session,
            UUID generationJobId,
            int questionOrder,
            InterviewQuestionType questionType,
            String questionCategory,
            String questionText
    ) {
        return new InterviewTurn(
                turnId,
                session,
                generationJobId,
                questionOrder,
                questionType,
                questionCategory,
                questionText
        );
    }

    @PrePersist
    void initializeTimestamps() {
        OffsetDateTime now = OffsetDateTime.now();
        createdAt = createdAt == null ? now : createdAt;
        updatedAt = updatedAt == null ? now : updatedAt;
    }

    @PreUpdate
    void updateTimestamp() {
        updatedAt = OffsetDateTime.now();
    }
}
