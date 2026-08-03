CREATE TABLE career_documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE RESTRICT,
    document_type VARCHAR(30) NOT NULL,
    original_file_name TEXT NOT NULL,
    storage_bucket VARCHAR(100) NOT NULL,
    storage_path TEXT NOT NULL UNIQUE,
    mime_type VARCHAR(100) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    processing_status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING',
    extracted_text TEXT,
    processing_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uq_career_documents_owner UNIQUE (user_id, document_id),
    CONSTRAINT chk_career_documents_type
        CHECK (document_type IN ('RESUME', 'COVER_LETTER')),
    CONSTRAINT chk_career_documents_status
        CHECK (processing_status IN ('PROCESSING', 'READY', 'FAILED')),
    CONSTRAINT chk_career_documents_file_size
        CHECK (file_size_bytes > 0)
);

CREATE INDEX idx_career_documents_owner
    ON career_documents (user_id, document_type, created_at DESC, document_id DESC)
    WHERE deleted_at IS NULL;
