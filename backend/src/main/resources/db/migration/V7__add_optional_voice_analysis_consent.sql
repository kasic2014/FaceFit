ALTER TABLE profiles
    ADD COLUMN voice_analysis_consent BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN voice_analysis_consented_at TIMESTAMPTZ,
    ADD CONSTRAINT chk_profiles_voice_analysis_consent
        CHECK (
            (voice_analysis_consent = TRUE AND voice_analysis_consented_at IS NOT NULL)
            OR (voice_analysis_consent = FALSE AND voice_analysis_consented_at IS NULL)
        );

ALTER TABLE interview_sessions
    ADD COLUMN voice_analysis_enabled BOOLEAN;

UPDATE interview_sessions sessions
SET voice_analysis_enabled = profiles.voice_analysis_consent
FROM profiles
WHERE profiles.user_id = sessions.user_id;

ALTER TABLE interview_sessions
    ALTER COLUMN voice_analysis_enabled SET DEFAULT FALSE,
    ALTER COLUMN voice_analysis_enabled SET NOT NULL;

ALTER TABLE interview_reports
    ALTER COLUMN speech_score DROP NOT NULL,
    DROP CONSTRAINT chk_interview_reports_scores,
    ADD CONSTRAINT chk_interview_reports_scores
        CHECK (
            overall_score BETWEEN 0 AND 100
            AND gaze_score BETWEEN 0 AND 100
            AND posture_score BETWEEN 0 AND 100
            AND (speech_score IS NULL OR speech_score BETWEEN 0 AND 100)
            AND content_score BETWEEN 0 AND 100
        );
