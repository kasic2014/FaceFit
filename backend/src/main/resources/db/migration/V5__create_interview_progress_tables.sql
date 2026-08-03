ALTER TABLE interview_sessions
    ADD COLUMN completion_type VARCHAR(30);

ALTER TABLE interview_sessions
    ADD CONSTRAINT chk_interview_sessions_completion_type
        CHECK (
            completion_type IS NULL
            OR completion_type IN ('NORMAL', 'USER_INTERRUPTED')
        );

CREATE TABLE interview_turns (
    turn_id UUID PRIMARY KEY,
    session_id UUID NOT NULL
        REFERENCES interview_sessions(session_id) ON DELETE RESTRICT,
    generation_job_id UUID NOT NULL,
    question_order INTEGER NOT NULL,
    question_type VARCHAR(30) NOT NULL,
    question_category VARCHAR(100) NOT NULL,
    question_text VARCHAR(500) NOT NULL,
    required BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_interview_turns_session_order
        UNIQUE (session_id, question_order),
    CONSTRAINT uq_interview_turns_session_text
        UNIQUE (session_id, question_text),
    CONSTRAINT uq_interview_turns_id_session
        UNIQUE (turn_id, session_id),
    CONSTRAINT chk_interview_turns_order
        CHECK (question_order BETWEEN 1 AND 10),
    CONSTRAINT chk_interview_turns_type
        CHECK (
            question_type IN (
                'INTRODUCTION',
                'EXPERIENCE',
                'JOB_ROLE',
                'BEHAVIORAL',
                'CLOSING'
            )
        ),
    CONSTRAINT chk_interview_turns_category
        CHECK (char_length(btrim(question_category)) BETWEEN 1 AND 100),
    CONSTRAINT chk_interview_turns_text
        CHECK (char_length(btrim(question_text)) BETWEEN 1 AND 500)
);

CREATE TABLE api_idempotency_records (
    idempotency_record_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE RESTRICT,
    http_method VARCHAR(10) NOT NULL,
    request_uri VARCHAR(500) NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    processing_status VARCHAR(20) NOT NULL DEFAULT 'PROCESSING',
    response_http_status INTEGER,
    response_body TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    row_version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_api_idempotency_scope
        UNIQUE (user_id, http_method, request_uri, idempotency_key),
    CONSTRAINT chk_api_idempotency_method
        CHECK (http_method IN ('POST')),
    CONSTRAINT chk_api_idempotency_key
        CHECK (
            char_length(idempotency_key) BETWEEN 8 AND 64
            AND idempotency_key ~ '^[A-Za-z0-9._:-]+$'
        ),
    CONSTRAINT chk_api_idempotency_hash
        CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_api_idempotency_status
        CHECK (processing_status IN ('PROCESSING', 'COMPLETED')),
    CONSTRAINT chk_api_idempotency_response
        CHECK (
            (
                processing_status = 'PROCESSING'
                AND response_http_status IS NULL
                AND response_body IS NULL
                AND completed_at IS NULL
            )
            OR (
                processing_status = 'COMPLETED'
                AND response_http_status IS NOT NULL
                AND response_body IS NOT NULL
                AND completed_at IS NOT NULL
            )
        )
);

CREATE TABLE interview_answers (
    answer_id UUID PRIMARY KEY,
    session_id UUID NOT NULL
        REFERENCES interview_sessions(session_id) ON DELETE RESTRICT,
    turn_id UUID NOT NULL,
    user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE RESTRICT,
    storage_bucket VARCHAR(100) NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type VARCHAR(100) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    file_sha256 VARCHAR(64) NOT NULL,
    recorded_duration_seconds INTEGER NOT NULL,
    detected_duration_millis BIGINT NOT NULL,
    ended_by VARCHAR(30) NOT NULL,
    answer_status VARCHAR(30) NOT NULL DEFAULT 'UPLOADING',
    transcript TEXT,
    next_question_ready BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    confirmed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT fk_interview_answers_turn_session
        FOREIGN KEY (turn_id, session_id)
        REFERENCES interview_turns(turn_id, session_id)
        ON DELETE RESTRICT,
    CONSTRAINT uq_interview_answers_turn UNIQUE (turn_id),
    CONSTRAINT uq_interview_answers_storage_path UNIQUE (storage_path),
    CONSTRAINT chk_interview_answers_mime
        CHECK (mime_type IN ('video/mp4', 'video/webm')),
    CONSTRAINT chk_interview_answers_size
        CHECK (file_size_bytes BETWEEN 1 AND 209715200),
    CONSTRAINT chk_interview_answers_sha256
        CHECK (file_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chk_interview_answers_recorded_duration
        CHECK (recorded_duration_seconds BETWEEN 1 AND 300),
    CONSTRAINT chk_interview_answers_detected_duration
        CHECK (detected_duration_millis BETWEEN 1 AND 300000),
    CONSTRAINT chk_interview_answers_ended_by
        CHECK (ended_by IN ('USER_BUTTON', 'SILENCE_DETECTED')),
    CONSTRAINT chk_interview_answers_status
        CHECK (
            answer_status IN (
                'UPLOADING',
                'QUEUED',
                'PROCESSING',
                'COMPLETED',
                'FAILED'
            )
        )
);

CREATE TABLE interview_processing_jobs (
    job_id UUID PRIMARY KEY,
    session_id UUID NOT NULL
        REFERENCES interview_sessions(session_id) ON DELETE RESTRICT,
    answer_id UUID REFERENCES interview_answers(answer_id) ON DELETE RESTRICT,
    job_type VARCHAR(30) NOT NULL,
    job_status VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    next_retry_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    worker_token UUID,
    locked_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failure_code VARCHAR(100),
    failure_retryable BOOLEAN,
    result_payload TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    row_version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_interview_processing_jobs_type
        CHECK (
            job_type IN (
                'QUESTION_GENERATION',
                'STT',
                'CV',
                'VOICE',
                'CONTENT'
            )
        ),
    CONSTRAINT chk_interview_processing_jobs_target
        CHECK (
            (job_type = 'QUESTION_GENERATION' AND answer_id IS NULL)
            OR (job_type <> 'QUESTION_GENERATION' AND answer_id IS NOT NULL)
        ),
    CONSTRAINT chk_interview_processing_jobs_status
        CHECK (job_status IN ('QUEUED', 'PROCESSING', 'SUCCEEDED', 'FAILED')),
    CONSTRAINT chk_interview_processing_jobs_attempts
        CHECK (
            max_attempts = 3
            AND attempt_count BETWEEN 0 AND max_attempts
        ),
    CONSTRAINT chk_interview_processing_jobs_claim
        CHECK (
            (
                job_status = 'PROCESSING'
                AND worker_token IS NOT NULL
                AND locked_at IS NOT NULL
            )
            OR (
                job_status <> 'PROCESSING'
                AND worker_token IS NULL
                AND locked_at IS NULL
            )
        )
);

ALTER TABLE interview_turns
    ADD CONSTRAINT fk_interview_turns_generation_job
        FOREIGN KEY (generation_job_id)
        REFERENCES interview_processing_jobs(job_id)
        ON DELETE RESTRICT;

CREATE UNIQUE INDEX uq_interview_jobs_active_question_generation
    ON interview_processing_jobs (session_id, job_type)
    WHERE job_type = 'QUESTION_GENERATION'
      AND job_status IN ('QUEUED', 'PROCESSING');

CREATE UNIQUE INDEX uq_interview_jobs_answer_type
    ON interview_processing_jobs (answer_id, job_type)
    WHERE answer_id IS NOT NULL;

CREATE INDEX idx_interview_turns_current
    ON interview_turns (session_id, question_order, turn_id);

CREATE INDEX idx_interview_answers_owner
    ON interview_answers (user_id, created_at DESC, answer_id DESC);

CREATE INDEX idx_interview_answers_session_status
    ON interview_answers (session_id, answer_status, turn_id);

CREATE INDEX idx_interview_jobs_due
    ON interview_processing_jobs (job_status, next_retry_at, created_at)
    WHERE job_status IN ('QUEUED', 'PROCESSING');

CREATE INDEX idx_interview_jobs_session
    ON interview_processing_jobs (session_id, job_type, job_status);

CREATE INDEX idx_api_idempotency_lookup
    ON api_idempotency_records (user_id, http_method, request_uri, idempotency_key);
