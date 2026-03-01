-- Migration: copilot_scoped_policies
-- Adds scoped policy tables for model access, feature flags, and connection permissions.

CREATE SCHEMA IF NOT EXISTS copilot;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================
-- Scoped Model Access Policies
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.model_access_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    scope_type VARCHAR(16) NOT NULL
        CHECK (scope_type IN ('account', 'group', 'team', 'user')),
    scope_id TEXT NOT NULL,
    mode VARCHAR(32) NOT NULL DEFAULT 'inherit'
        CHECK (mode IN ('inherit', 'allowlist', 'all_available', 'deny_all')),
    selected_models TEXT[] NOT NULL DEFAULT '{}',
    notes TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_model_access_policy_scope'
    ) THEN
        CREATE UNIQUE INDEX uq_copilot_model_access_policy_scope
            ON copilot.model_access_policies(account_id, scope_type, scope_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_model_access_policy_account
    ON copilot.model_access_policies(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_model_access_policy_scope
    ON copilot.model_access_policies(scope_type, scope_id);

-- ============================================
-- Scoped Feature Flag Policies
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.feature_flag_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    scope_type VARCHAR(16) NOT NULL
        CHECK (scope_type IN ('account', 'group', 'team', 'user')),
    scope_id TEXT NOT NULL,
    flags JSONB NOT NULL DEFAULT '{}',
    notes TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_feature_flag_policy_scope'
    ) THEN
        CREATE UNIQUE INDEX uq_copilot_feature_flag_policy_scope
            ON copilot.feature_flag_policies(account_id, scope_type, scope_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_feature_flag_policy_account
    ON copilot.feature_flag_policies(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_feature_flag_policy_scope
    ON copilot.feature_flag_policies(scope_type, scope_id);
CREATE INDEX IF NOT EXISTS idx_copilot_feature_flag_policy_flags
    ON copilot.feature_flag_policies USING gin(flags);

-- ============================================
-- Scoped Connection Permission Policies
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.connection_permission_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    scope_type VARCHAR(16) NOT NULL
        CHECK (scope_type IN ('account', 'group', 'team', 'user')),
    scope_id TEXT NOT NULL,
    connection_type VARCHAR(16) NOT NULL
        CHECK (connection_type IN ('all', 'mcp', 'openapi', 'integration')),
    permission_mode VARCHAR(40) NOT NULL DEFAULT 'admin_managed_use_only'
        CHECK (permission_mode IN ('admin_managed_use_only', 'self_managed_allowed')),
    allow_use_admin_connections BOOLEAN NOT NULL DEFAULT true,
    notes TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_conn_permission_policy_scope'
    ) THEN
        CREATE UNIQUE INDEX uq_copilot_conn_permission_policy_scope
            ON copilot.connection_permission_policies(account_id, scope_type, scope_id, connection_type);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_conn_permission_policy_account
    ON copilot.connection_permission_policies(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_conn_permission_policy_scope
    ON copilot.connection_permission_policies(scope_type, scope_id);
