CREATE TABLE profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE RESTRICT,
    member_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    onboarding_status VARCHAR(20) NOT NULL DEFAULT 'NOT_STARTED',
    onboarding_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_profiles_member_status
        CHECK (member_status IN ('ACTIVE', 'BLOCKED', 'WITHDRAWN')),
    CONSTRAINT chk_profiles_onboarding_status
        CHECK (onboarding_status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED')),
    CONSTRAINT chk_profiles_onboarding_completion
        CHECK (
            (onboarding_status = 'COMPLETED' AND onboarding_completed_at IS NOT NULL)
            OR (onboarding_status <> 'COMPLETED' AND onboarding_completed_at IS NULL)
        )
);

CREATE TABLE legal_documents (
    legal_document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_type VARCHAR(40) NOT NULL,
    legal_action_type VARCHAR(20) NOT NULL,
    title VARCHAR(200) NOT NULL,
    version VARCHAR(30) NOT NULL,
    content TEXT NOT NULL,
    is_onboarding_required BOOLEAN NOT NULL DEFAULT TRUE,
    is_current BOOLEAN NOT NULL DEFAULT FALSE,
    effective_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_legal_documents_version UNIQUE (document_type, version),
    CONSTRAINT chk_legal_documents_action
        CHECK (legal_action_type IN ('CONSENT', 'NOTICE'))
);

CREATE UNIQUE INDEX uq_legal_documents_current_type
    ON legal_documents (document_type)
    WHERE is_current = TRUE;

CREATE TABLE user_legal_records (
    legal_record_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE RESTRICT,
    legal_document_id UUID NOT NULL
        REFERENCES legal_documents(legal_document_id) ON DELETE RESTRICT,
    action_type VARCHAR(20) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    collection_method VARCHAR(30) NOT NULL DEFAULT 'WEB_CHECKBOX',
    ip_address INET,
    user_agent TEXT,
    CONSTRAINT chk_user_legal_records_action
        CHECK (action_type IN ('CONSENTED', 'ACKNOWLEDGED', 'WITHDRAWN'))
);

CREATE INDEX idx_user_legal_records_latest
    ON user_legal_records (user_id, legal_document_id, recorded_at DESC);
