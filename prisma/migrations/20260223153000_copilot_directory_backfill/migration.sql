-- Backfill copilot directory tables for environments where the
-- original copilot schema migration was already applied before these
-- tables were added.

CREATE SCHEMA IF NOT EXISTS copilot;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

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
