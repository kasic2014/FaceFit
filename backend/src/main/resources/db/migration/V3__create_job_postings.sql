CREATE TABLE job_postings (
    job_posting_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE RESTRICT,
    input_type VARCHAR(10) NOT NULL,
    original_file_name TEXT,
    storage_bucket VARCHAR(100),
    storage_path TEXT UNIQUE,
    mime_type VARCHAR(100),
    file_size_bytes BIGINT,
    raw_text TEXT,
    extracted_text TEXT,
    company_name TEXT,
    target_role TEXT,
    main_responsibilities TEXT,
    qualifications TEXT,
    preferred_qualifications TEXT,
    technologies_tools TEXT,
    core_competencies TEXT,
    company_business_intro TEXT,
    processing_status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING',
    processing_error VARCHAR(80),
    processing_attempt_count INTEGER NOT NULL DEFAULT 0,
    processing_started_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    row_version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_job_postings_input_type
        CHECK (input_type IN ('FILE', 'TEXT')),
    CONSTRAINT chk_job_postings_status
        CHECK (processing_status IN ('PROCESSING', 'READY', 'FAILED')),
    CONSTRAINT chk_job_postings_attempt_count
        CHECK (processing_attempt_count >= 0),
    CONSTRAINT chk_job_postings_raw_text_length
        CHECK (raw_text IS NULL OR char_length(raw_text) <= 50000),
    CONSTRAINT chk_job_postings_extracted_text_length
        CHECK (extracted_text IS NULL OR char_length(extracted_text) <= 50000),
    CONSTRAINT chk_job_postings_input_payload
        CHECK (
            (
                input_type = 'FILE'
                AND original_file_name IS NOT NULL
                AND storage_bucket IS NOT NULL
                AND storage_path IS NOT NULL
                AND mime_type IS NOT NULL
                AND file_size_bytes IS NOT NULL
                AND file_size_bytes > 0
                AND raw_text IS NULL
            )
            OR
            (
                input_type = 'TEXT'
                AND raw_text IS NOT NULL
                AND char_length(btrim(raw_text)) > 0
                AND original_file_name IS NULL
                AND storage_bucket IS NULL
                AND storage_path IS NULL
                AND mime_type IS NULL
                AND file_size_bytes IS NULL
            )
        )
);

CREATE INDEX idx_job_postings_owner_status_created
    ON job_postings (
        user_id,
        processing_status,
        created_at DESC,
        job_posting_id DESC
    )
    WHERE deleted_at IS NULL;
