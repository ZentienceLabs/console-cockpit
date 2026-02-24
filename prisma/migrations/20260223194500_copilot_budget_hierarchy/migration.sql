-- Migration: copilot_budget_hierarchy
-- Adds non-destructive fields to support hierarchical credit allocation.

ALTER TABLE copilot.credit_budget
    ADD COLUMN IF NOT EXISTS parent_budget_id UUID REFERENCES copilot.credit_budget(id) ON DELETE SET NULL;

ALTER TABLE copilot.credit_budget
    ADD COLUMN IF NOT EXISTS allocation_strategy VARCHAR(32) NOT NULL DEFAULT 'manual';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_credit_budget_allocation_strategy'
    ) THEN
        ALTER TABLE copilot.credit_budget
            ADD CONSTRAINT chk_credit_budget_allocation_strategy
            CHECK (allocation_strategy IN ('manual', 'equal_distribution', 'override'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_credit_budget_parent_budget_id
    ON copilot.credit_budget(parent_budget_id);
