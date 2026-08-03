CREATE TABLE interview_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE RESTRICT,
    resume_document_id UUID NOT NULL
        REFERENCES career_documents(document_id) ON DELETE RESTRICT,
    cover_letter_document_id UUID
        REFERENCES career_documents(document_id) ON DELETE RESTRICT,
    job_posting_id UUID NOT NULL
        REFERENCES job_postings(job_posting_id) ON DELETE RESTRICT,
    persona VARCHAR(50) NOT NULL,
    difficulty VARCHAR(30) NOT NULL,
    session_status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    snapshot_company_name TEXT NOT NULL,
    snapshot_target_role TEXT NOT NULL,
    snapshot_main_responsibilities TEXT NOT NULL,
    snapshot_qualifications TEXT NOT NULL,
    snapshot_preferred_qualifications TEXT,
    snapshot_technologies_tools TEXT,
    snapshot_core_competencies TEXT,
    snapshot_company_business_intro TEXT,
    current_question_order INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    interview_completed_at TIMESTAMPTZ,
    analysis_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    interrupted_at TIMESTAMPTZ,
    row_version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_interview_sessions_status
        CHECK (
            session_status IN (
                'DRAFT',
                'IN_PROGRESS',
                'INTERVIEW_COMPLETED',
                'ANALYZING',
                'COMPLETED',
                'INTERRUPTED'
            )
        ),
    CONSTRAINT chk_interview_sessions_documents_distinct
        CHECK (
            cover_letter_document_id IS NULL
            OR resume_document_id <> cover_letter_document_id
        ),
    CONSTRAINT chk_interview_sessions_persona
        CHECK (char_length(btrim(persona)) BETWEEN 1 AND 50),
    CONSTRAINT chk_interview_sessions_difficulty
        CHECK (char_length(btrim(difficulty)) BETWEEN 1 AND 30),
    CONSTRAINT chk_interview_sessions_snapshot_required
        CHECK (
            char_length(btrim(snapshot_company_name)) > 0
            AND char_length(btrim(snapshot_target_role)) > 0
            AND char_length(btrim(snapshot_main_responsibilities)) > 0
            AND char_length(btrim(snapshot_qualifications)) > 0
        ),
    CONSTRAINT chk_interview_sessions_current_question_order
        CHECK (current_question_order IS NULL OR current_question_order > 0)
);

CREATE INDEX idx_interview_sessions_owner
    ON interview_sessions (user_id, created_at DESC, session_id DESC);

CREATE INDEX idx_interview_sessions_job_reference
    ON interview_sessions (job_posting_id, session_status);

CREATE INDEX idx_interview_sessions_resume_reference
    ON interview_sessions (resume_document_id, session_status);

CREATE INDEX idx_interview_sessions_cover_reference
    ON interview_sessions (cover_letter_document_id, session_status)
    WHERE cover_letter_document_id IS NOT NULL;
