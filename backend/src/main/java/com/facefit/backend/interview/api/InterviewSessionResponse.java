package com.facefit.backend.interview.api;

import com.facefit.backend.interview.domain.InterviewSession;
import com.facefit.backend.interview.domain.InterviewSessionStatus;
import com.facefit.backend.interview.domain.InterviewCompletionType;

import java.time.OffsetDateTime;
import java.util.UUID;

public record InterviewSessionResponse(
        UUID sessionId,
        UUID resumeDocumentId,
        UUID coverLetterDocumentId,
        UUID jobPostingId,
        String persona,
        String difficulty,
        InterviewSessionStatus status,
        String companyName,
        String targetRole,
        String mainResponsibilities,
        String qualifications,
        String preferredQualifications,
        String technologiesTools,
        String coreCompetencies,
        String companyBusinessIntro,
        Integer currentQuestionOrder,
        boolean voiceAnalysisEnabled,
        InterviewCompletionType completionType,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt,
        OffsetDateTime startedAt,
        OffsetDateTime interviewCompletedAt,
        OffsetDateTime analysisStartedAt,
        OffsetDateTime completedAt,
        OffsetDateTime interruptedAt
) {

    public static InterviewSessionResponse from(InterviewSession session) {
        return new InterviewSessionResponse(
                session.getSessionId(),
                session.getResumeDocument().getDocumentId(),
                session.getCoverLetterDocument() == null
                        ? null
                        : session.getCoverLetterDocument().getDocumentId(),
                session.getJobPosting().getJobPostingId(),
                session.getPersona(),
                session.getDifficulty(),
                session.getStatus(),
                session.getCompanyName(),
                session.getTargetRole(),
                session.getMainResponsibilities(),
                session.getQualifications(),
                session.getPreferredQualifications(),
                session.getTechnologiesTools(),
                session.getCoreCompetencies(),
                session.getCompanyBusinessIntro(),
                session.getCurrentQuestionOrder(),
                session.isVoiceAnalysisEnabled(),
                session.getCompletionType(),
                session.getCreatedAt(),
                session.getUpdatedAt(),
                session.getStartedAt(),
                session.getInterviewCompletedAt(),
                session.getAnalysisStartedAt(),
                session.getCompletedAt(),
                session.getInterruptedAt()
        );
    }
}
