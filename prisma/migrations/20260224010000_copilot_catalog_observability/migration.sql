-- Copilot centralized catalogs + observability audit log
-- Non-destructive additions for model governance, integration visibility, and auditability.

CREATE SCHEMA IF NOT EXISTS copilot;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================
-- Copilot Model Catalog (super-admin managed)
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.model_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    provider VARCHAR(100),
    source VARCHAR(64) NOT NULL DEFAULT 'copilot',
    upstream_model_name VARCHAR(255),
    credits_per_1k_tokens NUMERIC(18,6) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_model_catalog_model_name') THEN
        CREATE UNIQUE INDEX uq_copilot_model_catalog_model_name
            ON copilot.model_catalog(lower(model_name));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_model_catalog_active
    ON copilot.model_catalog(is_active);
CREATE INDEX IF NOT EXISTS idx_copilot_model_catalog_provider
    ON copilot.model_catalog(provider);

-- ============================================
-- Copilot Integration Catalog (Composio visibility)
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.integration_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_key VARCHAR(255) NOT NULL,
    provider VARCHAR(64) NOT NULL DEFAULT 'composio',
    name VARCHAR(255) NOT NULL,
    description TEXT,
    toolkit VARCHAR(255),
    auth_config_id VARCHAR(255),
    icon VARCHAR(128),
    color VARCHAR(128),
    is_active BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_integration_catalog_key') THEN
        CREATE UNIQUE INDEX uq_copilot_integration_catalog_key
            ON copilot.integration_catalog(lower(integration_key));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_integration_catalog_active
    ON copilot.integration_catalog(is_active);
CREATE INDEX IF NOT EXISTS idx_copilot_integration_catalog_provider
    ON copilot.integration_catalog(provider);

-- ============================================
-- Copilot Audit Log (management + usage events)
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT,
    event_type VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL DEFAULT 'info'
        CHECK (severity IN ('debug','info','warning','error','critical')),
    resource_type VARCHAR(64),
    resource_id TEXT,
    action VARCHAR(64),
    actor_id TEXT,
    actor_email TEXT,
    message TEXT,
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_copilot_audit_log_account_time
    ON copilot.audit_log(account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_copilot_audit_log_event_time
    ON copilot.audit_log(event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_copilot_audit_log_severity_time
    ON copilot.audit_log(severity, created_at DESC);
