ALTER TABLE interview_answers
    ADD COLUMN storage_provider VARCHAR(20) NOT NULL DEFAULT 'SUPABASE',
    ADD COLUMN storage_url TEXT;

ALTER TABLE interview_answers
    ADD CONSTRAINT ck_interview_answers_storage_provider
        CHECK (storage_provider IN ('SUPABASE', 'NCLOUD')),
    ADD CONSTRAINT ck_interview_answers_storage_url
        CHECK (
            (storage_provider = 'SUPABASE' AND storage_url IS NULL)
            OR (
                storage_url IS NOT NULL
                AND storage_url LIKE 'https://%'
                AND POSITION('?' IN storage_url) = 0
            )
        );

COMMENT ON COLUMN interview_answers.storage_path IS
    'Provider-specific permanent object key; never a presigned URL';
COMMENT ON COLUMN interview_answers.storage_url IS
    'Canonical object URL without signature query parameters';
