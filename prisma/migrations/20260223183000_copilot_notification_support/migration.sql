-- Copilot notification templates + support tickets tables
-- Idempotent schema backfill for centralized cockpit management features.

CREATE SCHEMA IF NOT EXISTS copilot;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS copilot.notification_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    template_id VARCHAR(255),
    title_line VARCHAR(500) NOT NULL,
    template_content TEXT NOT NULL,
    event_id VARCHAR(255),
    type VARCHAR(20) NOT NULL DEFAULT 'EMAIL'
        CHECK (type IN ('EMAIL','PUSH','SMS','IN_APP')),
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'uq_copilot_notification_templates_account_template_id') THEN
        CREATE UNIQUE INDEX uq_copilot_notification_templates_account_template_id
            ON copilot.notification_templates(account_id, lower(template_id))
            WHERE template_id IS NOT NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_copilot_notification_templates_account
    ON copilot.notification_templates(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_notification_templates_event
    ON copilot.notification_templates(account_id, event_id);
CREATE INDEX IF NOT EXISTS idx_copilot_notification_templates_type
    ON copilot.notification_templates(account_id, type);

CREATE TABLE IF NOT EXISTS copilot.support_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id TEXT NOT NULL,
    user_profile_id TEXT,
    subject VARCHAR(500) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN','IN_PROGRESS','PENDING','RESOLVED','CLOSED','CANCELLED')),
    priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM'
        CHECK (priority IN ('LOW','MEDIUM','URGENT','IMPORTANT')),
    assigned_to TEXT,
    created_by TEXT,
    updated_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_copilot_support_tickets_account
    ON copilot.support_tickets(account_id);
CREATE INDEX IF NOT EXISTS idx_copilot_support_tickets_user
    ON copilot.support_tickets(account_id, user_profile_id);
CREATE INDEX IF NOT EXISTS idx_copilot_support_tickets_status
    ON copilot.support_tickets(account_id, status);
CREATE INDEX IF NOT EXISTS idx_copilot_support_tickets_priority
    ON copilot.support_tickets(account_id, priority);
CREATE INDEX IF NOT EXISTS idx_copilot_support_tickets_assigned
    ON copilot.support_tickets(account_id, assigned_to);
CREATE INDEX IF NOT EXISTS idx_copilot_support_tickets_created
    ON copilot.support_tickets(account_id, created_at DESC);
