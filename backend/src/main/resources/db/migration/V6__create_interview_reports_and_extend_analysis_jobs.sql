ALTER TABLE interview_answers
    ADD COLUMN transcript_schema_version VARCHAR(20);

UPDATE interview_answers
SET transcript_schema_version = '1.0'
WHERE transcript IS NOT NULL;

ALTER TABLE interview_answers
    ADD CONSTRAINT chk_interview_answers_transcript_version
        CHECK (
            (transcript IS NULL AND transcript_schema_version IS NULL)
            OR (
                transcript IS NOT NULL
                AND char_length(btrim(transcript_schema_version)) BETWEEN 1 AND 20
            )
        ),
    ADD CONSTRAINT uq_interview_answers_id_session
        UNIQUE (answer_id, session_id);

ALTER TABLE interview_processing_jobs
    DROP CONSTRAINT chk_interview_processing_jobs_type,
    DROP CONSTRAINT chk_interview_processing_jobs_target;

ALTER TABLE interview_processing_jobs
    ADD CONSTRAINT chk_interview_processing_jobs_type
        CHECK (
            job_type IN (
                'QUESTION_GENERATION',
                'STT',
                'CV',
                'VOICE',
                'CONTENT',
                'REPORT_GENERATION'
            )
        ),
    ADD CONSTRAINT chk_interview_processing_jobs_target
        CHECK (
            (
                job_type IN ('QUESTION_GENERATION', 'REPORT_GENERATION')
                AND answer_id IS NULL
            )
            OR (
                job_type IN ('STT', 'CV', 'VOICE', 'CONTENT')
                AND answer_id IS NOT NULL
            )
        );

CREATE TABLE interview_analysis_results (
    analysis_result_id UUID PRIMARY KEY,
    session_id UUID NOT NULL
        REFERENCES interview_sessions(session_id) ON DELETE RESTRICT,
    answer_id UUID NOT NULL,
    source_job_id UUID NOT NULL
        REFERENCES interview_processing_jobs(job_id) ON DELETE RESTRICT,
    analysis_type VARCHAR(20) NOT NULL,
    schema_version VARCHAR(20) NOT NULL,
    gaze_score NUMERIC(4, 1),
    posture_score NUMERIC(4, 1),
    speech_score NUMERIC(4, 1),
    content_score NUMERIC(4, 1),
    public_feedback JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_interview_analysis_results_answer_session
        FOREIGN KEY (answer_id, session_id)
        REFERENCES interview_answers(answer_id, session_id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_interview_analysis_results_job UNIQUE (source_job_id),
    CONSTRAINT uq_interview_analysis_results_answer_type
        UNIQUE (answer_id, analysis_type),
    CONSTRAINT chk_interview_analysis_results_type
        CHECK (analysis_type IN ('CV', 'VOICE', 'CONTENT')),
    CONSTRAINT chk_interview_analysis_results_schema
        CHECK (char_length(btrim(schema_version)) BETWEEN 1 AND 20),
    CONSTRAINT chk_interview_analysis_results_feedback
        CHECK (jsonb_typeof(public_feedback) = 'array'),
    CONSTRAINT chk_interview_analysis_results_scores
        CHECK (
            (gaze_score IS NULL OR gaze_score BETWEEN 0 AND 100)
            AND (posture_score IS NULL OR posture_score BETWEEN 0 AND 100)
            AND (speech_score IS NULL OR speech_score BETWEEN 0 AND 100)
            AND (content_score IS NULL OR content_score BETWEEN 0 AND 100)
        ),
    CONSTRAINT chk_interview_analysis_results_shape
        CHECK (
            (
                analysis_type = 'CV'
                AND gaze_score IS NOT NULL
                AND posture_score IS NOT NULL
                AND speech_score IS NULL
                AND content_score IS NULL
            )
            OR (
                analysis_type = 'VOICE'
                AND gaze_score IS NULL
                AND posture_score IS NULL
                AND speech_score IS NOT NULL
                AND content_score IS NULL
            )
            OR (
                analysis_type = 'CONTENT'
                AND gaze_score IS NULL
                AND posture_score IS NULL
                AND speech_score IS NULL
                AND content_score IS NOT NULL
            )
        )
);

CREATE TABLE interview_reports (
    report_id UUID PRIMARY KEY,
    session_id UUID NOT NULL
        REFERENCES interview_sessions(session_id) ON DELETE RESTRICT,
    schema_version VARCHAR(20) NOT NULL,
    input_hash VARCHAR(64) NOT NULL,
    overall_score NUMERIC(4, 1) NOT NULL,
    gaze_score NUMERIC(4, 1) NOT NULL,
    posture_score NUMERIC(4, 1) NOT NULL,
    speech_score NUMERIC(4, 1) NOT NULL,
    content_score NUMERIC(4, 1) NOT NULL,
    strengths JSONB NOT NULL,
    improvements JSONB NOT NULL,
    question_feedback JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_interview_reports_session UNIQUE (session_id),
    CONSTRAINT chk_interview_reports_schema
        CHECK (char_length(btrim(schema_version)) BETWEEN 1 AND 20),
    CONSTRAINT chk_interview_reports_hash
        CHECK (input_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_interview_reports_scores
        CHECK (
            overall_score BETWEEN 0 AND 100
            AND gaze_score BETWEEN 0 AND 100
            AND posture_score BETWEEN 0 AND 100
            AND speech_score BETWEEN 0 AND 100
            AND content_score BETWEEN 0 AND 100
        ),
    CONSTRAINT chk_interview_reports_json
        CHECK (
            jsonb_typeof(strengths) = 'array'
            AND jsonb_typeof(improvements) = 'array'
            AND jsonb_typeof(question_feedback) = 'array'
        )
);

CREATE UNIQUE INDEX uq_interview_jobs_session_report
    ON interview_processing_jobs (session_id)
    WHERE job_type = 'REPORT_GENERATION';

CREATE INDEX idx_interview_analysis_results_session
    ON interview_analysis_results (session_id, answer_id, analysis_type);

CREATE INDEX idx_interview_reports_lookup
    ON interview_reports (session_id, generated_at DESC);

CREATE INDEX idx_interview_sessions_analysis_candidates
    ON interview_sessions (session_status, completion_type, updated_at)
    WHERE session_status IN ('INTERVIEW_COMPLETED', 'ANALYZING');
