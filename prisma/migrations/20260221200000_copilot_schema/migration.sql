-- Migration: copilot_schema
-- Creates the `copilot` PostgreSQL schema and all copilot-specific tables.
-- All statements are idempotent (IF NOT EXISTS / OR REPLACE guards).

-- ============================================
-- Schema
-- ============================================
CREATE SCHEMA IF NOT EXISTS copilot;

-- ============================================
-- Credit Budgets
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.credit_budget (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    budget_plan_id UUID,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('account','group','team','user')),
    scope_id UUID NOT NULL,
    allocated INTEGER NOT NULL DEFAULT 0 CHECK (allocated >= 0),
    limit_amount INTEGER NOT NULL DEFAULT 0 CHECK (limit_amount >= 0),
    overflow_cap INTEGER CHECK (overflow_cap >= 0),
    used INTEGER NOT NULL DEFAULT 0 CHECK (used >= 0),
    overflow_used INTEGER NOT NULL DEFAULT 0 CHECK (overflow_used >= 0),
    cycle_start TIMESTAMPTZ NOT NULL,
    cycle_end TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_cycle CHECK (cycle_end > cycle_start)
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_credit_budget_entity_cycle') THEN
        CREATE UNIQUE INDEX uq_credit_budget_entity_cycle
            ON copilot.credit_budget(scope_type, scope_id, cycle_start);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_credit_budget_account
    ON copilot.credit_budget(account_id);
CREATE INDEX IF NOT EXISTS idx_credit_budget_entity
    ON copilot.credit_budget(scope_type, scope_id);
CREATE INDEX IF NOT EXISTS idx_credit_budget_cycle
    ON copilot.credit_budget(cycle_start, cycle_end);

CREATE TABLE IF NOT EXISTS copilot.budget_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    name VARCHAR(255) NOT NULL DEFAULT 'Default Plan',
    is_active BOOLEAN NOT NULL DEFAULT true,
    distribution JSONB NOT NULL DEFAULT '{"groups":[],"teams":[],"users":[]}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_budget_plans_account
    ON copilot.budget_plans(account_id);

-- ============================================
-- Agent Definitions
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.agents_def (
    agent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    prompt TEXT,
    page VARCHAR(255),
    categories JSONB NOT NULL DEFAULT '{}',
    tags TEXT[] NOT NULL DEFAULT '{}',
    builtin_tools TEXT[] NOT NULL DEFAULT '{}',
    tools_mcp_ids UUID[] NOT NULL DEFAULT '{}',
    tools_openapi_ids UUID[] NOT NULL DEFAULT '{}',
    links JSONB NOT NULL DEFAULT '{"knowledge":{"file_ids":[],"mcp_ids":[],"openapi_ids":[]},"guardrails":{"file_ids":[],"mcp_ids":[],"openapi_ids":[]},"actions":{"file_ids":[],"mcp_ids":[],"openapi_ids":[]}}',
    is_singleton BOOLEAN NOT NULL DEFAULT false,
    is_non_conversational BOOLEAN NOT NULL DEFAULT false,
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    availability TEXT[] NOT NULL DEFAULT '{platform}',
    provider VARCHAR(100) NOT NULL DEFAULT 'PLATFORM',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agents_def_account ON copilot.agents_def(account_id);
CREATE INDEX IF NOT EXISTS idx_agents_def_name ON copilot.agents_def(name);
CREATE INDEX IF NOT EXISTS idx_agents_def_status ON copilot.agents_def(status);
CREATE INDEX IF NOT EXISTS idx_agents_def_categories ON copilot.agents_def USING gin(categories);
CREATE INDEX IF NOT EXISTS idx_agents_def_tags ON copilot.agents_def USING gin(tags);

-- ============================================
-- Agent Groups
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.agent_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT,
    group_code VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    group_type VARCHAR(50) NOT NULL DEFAULT 'custom',
    metadata JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_agent_groups_group_code') THEN
        CREATE UNIQUE INDEX uq_agent_groups_group_code ON copilot.agent_groups(group_code);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_agent_groups_account ON copilot.agent_groups(account_id);
CREATE INDEX IF NOT EXISTS idx_agent_groups_type ON copilot.agent_groups(group_type);

CREATE TABLE IF NOT EXISTS copilot.agent_group_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES copilot.agent_groups(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES copilot.agents_def(agent_id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_agent_group_members') THEN
        CREATE UNIQUE INDEX uq_agent_group_members ON copilot.agent_group_members(group_id, agent_id);
    END IF;
END $$;

-- ============================================
-- Marketplace Items (polymorphic)
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.marketplace_items (
    marketplace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT,
    entity_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL DEFAULT 'agent'
        CHECK (entity_type IN ('agent','mcp_server','openapi_spec','integration','workflow','prompt_template')),
    connection_id UUID,
    provider VARCHAR(100) NOT NULL DEFAULT 'PLATFORM',
    metadata JSONB NOT NULL DEFAULT '{}',
    title VARCHAR(255) NOT NULL,
    short_description VARCHAR(500),
    long_description TEXT,
    icon_url VARCHAR(500),
    banner_url VARCHAR(500),
    screenshots JSONB NOT NULL DEFAULT '[]',
    demo_video_url VARCHAR(500),
    author VARCHAR(255),
    author_url VARCHAR(500),
    version VARCHAR(50) NOT NULL DEFAULT '1.0.0',
    changelog JSONB NOT NULL DEFAULT '[]',
    pricing_model VARCHAR(20) NOT NULL DEFAULT 'free'
        CHECK (pricing_model IN ('free','paid','freemium')),
    price DECIMAL(10,2),
    installation_count INTEGER NOT NULL DEFAULT 0,
    rating_avg DECIMAL(3,2) CHECK (rating_avg IS NULL OR (rating_avg >= 0 AND rating_avg <= 5)),
    rating_count INTEGER NOT NULL DEFAULT 0,
    is_featured BOOLEAN NOT NULL DEFAULT false,
    is_verified BOOLEAN NOT NULL DEFAULT false,
    marketplace_status VARCHAR(20) NOT NULL DEFAULT 'draft'
        CHECK (marketplace_status IN ('draft','pending','published','rejected')),
    capabilities JSONB NOT NULL DEFAULT '[]',
    requirements JSONB NOT NULL DEFAULT '[]',
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_marketplace_items_account ON copilot.marketplace_items(account_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_items_entity ON copilot.marketplace_items(entity_id);
CREATE INDEX IF NOT EXISTS idx_marketplace_items_entity_type ON copilot.marketplace_items(entity_type);
CREATE INDEX IF NOT EXISTS idx_marketplace_items_status ON copilot.marketplace_items(marketplace_status);
CREATE INDEX IF NOT EXISTS idx_marketplace_items_featured ON copilot.marketplace_items(is_featured) WHERE is_featured = true;

-- ============================================
-- Account Connections
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.account_connections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    connection_type VARCHAR(20) NOT NULL CHECK (connection_type IN ('mcp','openapi','integration')),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    description_for_agent TEXT,
    connection_data JSONB NOT NULL DEFAULT '{}',
    is_active BOOLEAN NOT NULL DEFAULT true,
    is_default BOOLEAN NOT NULL DEFAULT false,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_account_connections_name') THEN
        CREATE UNIQUE INDEX uq_account_connections_name ON copilot.account_connections(account_id, name);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_account_connections_account ON copilot.account_connections(account_id);
CREATE INDEX IF NOT EXISTS idx_account_connections_type ON copilot.account_connections(account_id, connection_type);

-- ============================================
-- Enhanced Guardrails
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.guardrails_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    guard_type VARCHAR(20) NOT NULL CHECK (guard_type IN ('pii','toxic','jailbreak')),
    enabled BOOLEAN NOT NULL DEFAULT true,
    execution_order SMALLINT NOT NULL DEFAULT 1 CHECK (execution_order BETWEEN 1 AND 10),
    action_on_fail VARCHAR(20) NOT NULL DEFAULT 'block'
        CHECK (action_on_fail IN ('block','flag','log_only')),
    config JSONB NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_guardrails_config_account_guard') THEN
        CREATE UNIQUE INDEX uq_guardrails_config_account_guard ON copilot.guardrails_config(account_id, guard_type);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_guardrails_config_account ON copilot.guardrails_config(account_id);

CREATE TABLE IF NOT EXISTS copilot.guardrails_custom_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT,
    guard_type VARCHAR(20) NOT NULL CHECK (guard_type IN ('pii','jailbreak')),
    pattern_name VARCHAR(255) NOT NULL,
    pattern_regex TEXT NOT NULL,
    pattern_type VARCHAR(20) NOT NULL DEFAULT 'detect'
        CHECK (pattern_type IN ('detect','block','allow')),
    action VARCHAR(20) NOT NULL DEFAULT 'mask'
        CHECK (action IN ('mask','redact','hash','block')),
    enabled BOOLEAN NOT NULL DEFAULT true,
    is_system BOOLEAN NOT NULL DEFAULT false,
    category VARCHAR(100),
    description TEXT,
    severity VARCHAR(20) DEFAULT 'medium'
        CHECK (severity IN ('low','medium','high','critical')),
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_guardrails_patterns_name') THEN
        CREATE UNIQUE INDEX uq_guardrails_patterns_name ON copilot.guardrails_custom_patterns(account_id, guard_type, pattern_name);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_guardrails_patterns_account ON copilot.guardrails_custom_patterns(account_id);
CREATE INDEX IF NOT EXISTS idx_guardrails_patterns_system ON copilot.guardrails_custom_patterns(is_system) WHERE is_system = true;

CREATE TABLE IF NOT EXISTS copilot.guardrails_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    guard_type VARCHAR(20) NOT NULL,
    action VARCHAR(20) NOT NULL CHECK (action IN ('create','update','delete','enable','disable')),
    old_config JSONB,
    new_config JSONB,
    changed_fields TEXT[] NOT NULL DEFAULT '{}',
    changed_by TEXT,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_address INET,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_guardrails_audit_account_time ON copilot.guardrails_audit_log(account_id, changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_guardrails_audit_guard_time ON copilot.guardrails_audit_log(account_id, guard_type, changed_at DESC);

-- ============================================
-- Copilot User / Membership / Group / Team / Invite Management
-- ============================================
CREATE TABLE IF NOT EXISTS copilot.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    email VARCHAR(320) NOT NULL,
    name VARCHAR(255) NOT NULL,
    profile_image TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_users_account_email') THEN
        CREATE UNIQUE INDEX uq_copilot_users_account_email
            ON copilot.users(account_id, lower(email));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_users_account ON copilot.users(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_users_email ON copilot.users(lower(email));
CREATE INDEX IF NOT EXISTS idx_copilot_users_active ON copilot.users(account_id, is_active);

CREATE TABLE IF NOT EXISTS copilot.groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_default BOOLEAN NOT NULL DEFAULT false,
    owner_id UUID REFERENCES copilot.users(id) ON DELETE SET NULL,
    contact_email VARCHAR(320),
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_groups_account_name') THEN
        CREATE UNIQUE INDEX uq_copilot_groups_account_name
            ON copilot.groups(account_id, lower(name));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_groups_account ON copilot.groups(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_groups_default ON copilot.groups(account_id, is_default);

CREATE TABLE IF NOT EXISTS copilot.teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    group_id UUID NOT NULL REFERENCES copilot.groups(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    is_default BOOLEAN NOT NULL DEFAULT false,
    owner_id UUID REFERENCES copilot.users(id) ON DELETE SET NULL,
    contact_email VARCHAR(320),
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active','inactive')),
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_teams_group_name') THEN
        CREATE UNIQUE INDEX uq_copilot_teams_group_name
            ON copilot.teams(group_id, lower(name));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_teams_account ON copilot.teams(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_teams_group ON copilot.teams(group_id);
CREATE INDEX IF NOT EXISTS idx_copilot_teams_default ON copilot.teams(account_id, is_default);

CREATE TABLE IF NOT EXISTS copilot.account_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    user_id UUID NOT NULL REFERENCES copilot.users(id) ON DELETE CASCADE,
    app_role VARCHAR(20) NOT NULL DEFAULT 'USER'
        CHECK (app_role IN ('ADMIN','USER','GUEST','MEMBER','VIEWER')),
    team_id UUID REFERENCES copilot.teams(id) ON DELETE SET NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tenant_preferences JSONB NOT NULL DEFAULT '{}',
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_membership_account_user') THEN
        CREATE UNIQUE INDEX uq_copilot_membership_account_user
            ON copilot.account_memberships(account_id, user_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_membership_account ON copilot.account_memberships(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_membership_user ON copilot.account_memberships(user_id);
CREATE INDEX IF NOT EXISTS idx_copilot_membership_team ON copilot.account_memberships(team_id);
CREATE INDEX IF NOT EXISTS idx_copilot_membership_active ON copilot.account_memberships(account_id, is_active);

CREATE TABLE IF NOT EXISTS copilot.user_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    email VARCHAR(320) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'USER'
        CHECK (role IN ('ADMIN','USER','GUEST','MEMBER','VIEWER')),
    role_id TEXT,
    workspace_id TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','ACCEPTED','DECLINED','EXPIRED','CANCELLED')),
    token VARCHAR(128) NOT NULL,
    invitation_data JSONB NOT NULL DEFAULT '{}',
    created_by TEXT,
    accepted_by TEXT,
    accepted_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_invites_token') THEN
        CREATE UNIQUE INDEX uq_copilot_invites_token ON copilot.user_invites(token);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_invites_account ON copilot.user_invites(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_invites_status ON copilot.user_invites(account_id, status);
CREATE INDEX IF NOT EXISTS idx_copilot_invites_email ON copilot.user_invites(account_id, lower(email));
CREATE INDEX IF NOT EXISTS idx_copilot_invites_expires ON copilot.user_invites(expires_at);

-- ============================================
-- Aggregation Views
-- ============================================
CREATE OR REPLACE VIEW copilot.v_budget_summary AS
SELECT
    cb.account_id,
    cb.scope_type,
    cb.scope_id,
    SUM(cb.allocated) AS total_allocated,
    SUM(cb.used) AS total_used,
    SUM(cb.overflow_used) AS total_overflow_used,
    SUM(cb.limit_amount) AS total_limit,
    CASE
        WHEN SUM(cb.limit_amount) > 0
        THEN ROUND((SUM(cb.used)::NUMERIC / SUM(cb.limit_amount)::NUMERIC) * 100, 2)
        ELSE 0
    END AS usage_pct,
    MAX(cb.cycle_end) AS latest_cycle_end
FROM copilot.credit_budget cb
WHERE cb.cycle_end > now()
GROUP BY cb.account_id, cb.scope_type, cb.scope_id;

CREATE OR REPLACE VIEW copilot.v_budget_alerts AS
SELECT
    cb.account_id,
    cb.scope_type,
    cb.scope_id,
    cb.allocated,
    cb.limit_amount,
    cb.used,
    cb.overflow_used,
    cb.overflow_cap,
    cb.cycle_start,
    cb.cycle_end,
    CASE
        WHEN cb.limit_amount > 0 THEN ROUND((cb.used::NUMERIC / cb.limit_amount::NUMERIC) * 100, 2)
        ELSE 0
    END AS usage_pct,
    CASE
        WHEN cb.limit_amount > 0 AND cb.used >= cb.limit_amount THEN 'at_limit'
        WHEN cb.limit_amount > 0 AND cb.used::NUMERIC / cb.limit_amount::NUMERIC >= 0.95 THEN 'critical'
        WHEN cb.limit_amount > 0 AND cb.used::NUMERIC / cb.limit_amount::NUMERIC >= 0.80 THEN 'warning'
        ELSE 'ok'
    END AS alert_level
FROM copilot.credit_budget cb
WHERE cb.cycle_end > now()
  AND cb.limit_amount > 0
  AND cb.used::NUMERIC / cb.limit_amount::NUMERIC >= 0.80;
