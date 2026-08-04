package com.facefit.backend.member.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;
import org.hibernate.annotations.ColumnDefault;
import org.hibernate.annotations.DynamicInsert;
import org.hibernate.annotations.Generated;
import org.hibernate.generator.EventType;

import java.time.OffsetDateTime;
import java.util.Objects;
import java.util.UUID;

@Getter
@Entity
@DynamicInsert
@Table(name = "profiles")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class Profile {

    @Id
    @Column(name = "user_id", nullable = false, updatable = false)
    private UUID userId;

    @Enumerated(EnumType.STRING)
    @Generated(event = EventType.INSERT)
    @ColumnDefault("'ACTIVE'")
    @Column(name = "member_status", nullable = false, length = 20)
    private MemberStatus memberStatus;

    @Enumerated(EnumType.STRING)
    @Generated(event = EventType.INSERT)
    @ColumnDefault("'NOT_STARTED'")
    @Column(name = "onboarding_status", nullable = false, length = 20)
    private OnboardingStatus onboardingStatus;

    @Column(name = "onboarding_completed_at")
    private OffsetDateTime onboardingCompletedAt;

    @ColumnDefault("false")
    @Column(name = "voice_analysis_consent", nullable = false)
    private boolean voiceAnalysisConsent;

    @Column(name = "voice_analysis_consented_at")
    private OffsetDateTime voiceAnalysisConsentedAt;

    @Generated(event = EventType.INSERT)
    @ColumnDefault("now()")
    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @Generated(event = EventType.INSERT)
    @ColumnDefault("now()")
    @Column(name = "updated_at", nullable = false, updatable = false)
    private OffsetDateTime updatedAt;

    private Profile(UUID userId) {
        this.userId = Objects.requireNonNull(userId, "userId must not be null");
    }

    public static Profile withDatabaseDefaults(UUID userId) {
        return new Profile(userId);
    }

    public void changeMemberStatus(MemberStatus memberStatus) {
        this.memberStatus = Objects.requireNonNull(memberStatus, "memberStatus must not be null");
    }

    public void changeOnboardingStatus(
            OnboardingStatus onboardingStatus,
            OffsetDateTime onboardingCompletedAt
    ) {
        OnboardingStatus nextStatus = Objects.requireNonNull(
                onboardingStatus,
                "onboardingStatus must not be null"
        );
        boolean completed = nextStatus == OnboardingStatus.COMPLETED;
        if (completed != (onboardingCompletedAt != null)) {
            throw new IllegalArgumentException(
                    "COMPLETED 상태에만 onboardingCompletedAt 값이 필요합니다."
            );
        }

        this.onboardingStatus = nextStatus;
        this.onboardingCompletedAt = onboardingCompletedAt;
    }

    public void changeVoiceAnalysisConsent(
            boolean consent,
            OffsetDateTime consentedAt
    ) {
        if (consent != (consentedAt != null)) {
            throw new IllegalArgumentException(
                    "음성 분석 동의 시각은 동의한 경우에만 필요합니다."
            );
        }
        this.voiceAnalysisConsent = consent;
        this.voiceAnalysisConsentedAt = consentedAt;
    }

    public boolean isVoiceAnalysisConsented() {
        return voiceAnalysisConsent;
    }
}
