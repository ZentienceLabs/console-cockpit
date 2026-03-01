-- Control Plane V1: unified console-cockpit with explicit console/copilot domain separation

-- ---------- DOMAIN ORG/TREE (COPILOT) ----------
CREATE TABLE IF NOT EXISTS "Alchemi_CopilotOrgTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "is_default_global" BOOLEAN NOT NULL DEFAULT FALSE,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CopilotOrgTable_account_name_key" ON "Alchemi_CopilotOrgTable"("account_id", "name");
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotOrgTable_account_id_idx" ON "Alchemi_CopilotOrgTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotTeamTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "org_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_CopilotTeamTable_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "Alchemi_CopilotOrgTable"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CopilotTeamTable_org_name_key" ON "Alchemi_CopilotTeamTable"("org_id", "name");
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotTeamTable_account_id_idx" ON "Alchemi_CopilotTeamTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotUserTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "identity_user_id" TEXT,
  "email" TEXT,
  "display_name" TEXT,
  "status" TEXT NOT NULL DEFAULT 'active',
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CopilotUserTable_account_email_key" ON "Alchemi_CopilotUserTable"("account_id", "email");
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotUserTable_account_id_idx" ON "Alchemi_CopilotUserTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotTeamMembershipTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "team_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "role" TEXT NOT NULL DEFAULT 'member',
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_CopilotTeamMembershipTable_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "Alchemi_CopilotTeamTable"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "Alchemi_CopilotTeamMembershipTable_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "Alchemi_CopilotUserTable"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CopilotTeamMembershipTable_team_user_key" ON "Alchemi_CopilotTeamMembershipTable"("team_id", "user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotTeamMembershipTable_account_id_idx" ON "Alchemi_CopilotTeamMembershipTable"("account_id");

-- ---------- DOMAIN ORG/TREE (CONSOLE) ----------
CREATE TABLE IF NOT EXISTS "Alchemi_ConsoleOrgTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_ConsoleOrgTable_account_name_key" ON "Alchemi_ConsoleOrgTable"("account_id", "name");
CREATE INDEX IF NOT EXISTS "Alchemi_ConsoleOrgTable_account_id_idx" ON "Alchemi_ConsoleOrgTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_ConsoleTeamTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "org_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_ConsoleTeamTable_org_id_fkey" FOREIGN KEY ("org_id") REFERENCES "Alchemi_ConsoleOrgTable"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_ConsoleTeamTable_org_name_key" ON "Alchemi_ConsoleTeamTable"("org_id", "name");
CREATE INDEX IF NOT EXISTS "Alchemi_ConsoleTeamTable_account_id_idx" ON "Alchemi_ConsoleTeamTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_ConsoleUserTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "identity_user_id" TEXT,
  "email" TEXT,
  "display_name" TEXT,
  "status" TEXT NOT NULL DEFAULT 'active',
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_ConsoleUserTable_account_email_key" ON "Alchemi_ConsoleUserTable"("account_id", "email");
CREATE INDEX IF NOT EXISTS "Alchemi_ConsoleUserTable_account_id_idx" ON "Alchemi_ConsoleUserTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_ConsoleTeamMembershipTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "team_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "role" TEXT NOT NULL DEFAULT 'member',
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_ConsoleTeamMembershipTable_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "Alchemi_ConsoleTeamTable"("id") ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT "Alchemi_ConsoleTeamMembershipTable_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "Alchemi_ConsoleUserTable"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_ConsoleTeamMembershipTable_team_user_key" ON "Alchemi_ConsoleTeamMembershipTable"("team_id", "user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_ConsoleTeamMembershipTable_account_id_idx" ON "Alchemi_ConsoleTeamMembershipTable"("account_id");

-- ---------- BILLING / BUDGETS ----------
CREATE TABLE IF NOT EXISTS "Alchemi_AccountAllocationTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "monthly_credits" DOUBLE PRECISION NOT NULL DEFAULT 0,
  "overflow_limit" DOUBLE PRECISION NOT NULL DEFAULT 0,
  "credit_factor" DOUBLE PRECISION NOT NULL DEFAULT 1,
  "effective_from" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_AccountAllocationTable_account_id_fkey" FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccountAllocationTable_account_key" ON "Alchemi_AccountAllocationTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotBudgetPlanTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "cycle" TEXT NOT NULL DEFAULT 'monthly',
  "status" TEXT NOT NULL DEFAULT 'active',
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotBudgetPlanTable_account_id_idx" ON "Alchemi_CopilotBudgetPlanTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotBudgetAllocationTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "plan_id" TEXT NOT NULL,
  "scope_type" TEXT NOT NULL,
  "scope_id" TEXT NOT NULL,
  "allocated_credits" DOUBLE PRECISION NOT NULL DEFAULT 0,
  "overflow_cap" DOUBLE PRECISION,
  "source" TEXT NOT NULL DEFAULT 'manual',
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_CopilotBudgetAllocationTable_plan_id_fkey" FOREIGN KEY ("plan_id") REFERENCES "Alchemi_CopilotBudgetPlanTable"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CopilotBudgetAllocationTable_plan_scope_key" ON "Alchemi_CopilotBudgetAllocationTable"("plan_id", "scope_type", "scope_id");
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotBudgetAllocationTable_account_id_idx" ON "Alchemi_CopilotBudgetAllocationTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotBudgetOverrideTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "plan_id" TEXT NOT NULL,
  "scope_type" TEXT NOT NULL,
  "scope_id" TEXT NOT NULL,
  "override_credits" DOUBLE PRECISION NOT NULL,
  "reason" TEXT,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_CopilotBudgetOverrideTable_plan_id_fkey" FOREIGN KEY ("plan_id") REFERENCES "Alchemi_CopilotBudgetPlanTable"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotBudgetOverrideTable_account_id_idx" ON "Alchemi_CopilotBudgetOverrideTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotBudgetCycleTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "source_plan_id" TEXT NOT NULL,
  "new_plan_id" TEXT NOT NULL,
  "cycle_start" TIMESTAMP(3) NOT NULL,
  "cycle_end" TIMESTAMP(3) NOT NULL,
  "rollover_credits" DOUBLE PRECISION NOT NULL DEFAULT 0,
  "overflow_charge_credits" DOUBLE PRECISION NOT NULL DEFAULT 0,
  "summary_json" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotBudgetCycleTable_account_id_idx" ON "Alchemi_CopilotBudgetCycleTable"("account_id");

-- ---------- COPILOT RESOURCES ----------
CREATE TABLE IF NOT EXISTS "Alchemi_CopilotConnectionTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "connection_type" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "credential_visibility" TEXT NOT NULL DEFAULT 'use_only',
  "allow_user_self_manage" BOOLEAN NOT NULL DEFAULT FALSE,
  "config_json" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "secret_json" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotConnectionTable_account_id_idx" ON "Alchemi_CopilotConnectionTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotConnectionGrantTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "connection_id" TEXT NOT NULL,
  "scope_type" TEXT NOT NULL,
  "scope_id" TEXT NOT NULL,
  "can_manage" BOOLEAN NOT NULL DEFAULT FALSE,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_CopilotConnectionGrantTable_connection_id_fkey" FOREIGN KEY ("connection_id") REFERENCES "Alchemi_CopilotConnectionTable"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CopilotConnectionGrantTable_conn_scope_key" ON "Alchemi_CopilotConnectionGrantTable"("connection_id", "scope_type", "scope_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotGuardrailPresetTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "code" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "preset_json" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CopilotGuardrailPresetTable_account_code_key" ON "Alchemi_CopilotGuardrailPresetTable"("account_id", "code");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotGuardrailAssignmentTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "preset_id" TEXT NOT NULL,
  "scope_type" TEXT NOT NULL,
  "scope_id" TEXT NOT NULL,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_CopilotGuardrailAssignmentTable_preset_id_fkey" FOREIGN KEY ("preset_id") REFERENCES "Alchemi_CopilotGuardrailPresetTable"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotGuardrailAssignmentTable_account_id_idx" ON "Alchemi_CopilotGuardrailAssignmentTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotAgentTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "name" TEXT NOT NULL,
  "description" TEXT,
  "definition_json" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotAgentTable_account_id_idx" ON "Alchemi_CopilotAgentTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotAgentGrantTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "agent_id" TEXT NOT NULL,
  "scope_type" TEXT NOT NULL,
  "scope_id" TEXT NOT NULL,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT "Alchemi_CopilotAgentGrantTable_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "Alchemi_CopilotAgentTable"("id") ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CopilotAgentGrantTable_agent_scope_key" ON "Alchemi_CopilotAgentGrantTable"("agent_id", "scope_type", "scope_id");

CREATE TABLE IF NOT EXISTS "Alchemi_ModelGrantTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "domain" TEXT NOT NULL,
  "model_name" TEXT NOT NULL,
  "scope_type" TEXT NOT NULL,
  "scope_id" TEXT NOT NULL,
  "access_mode" TEXT NOT NULL DEFAULT 'allow',
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "Alchemi_ModelGrantTable_account_domain_idx" ON "Alchemi_ModelGrantTable"("account_id", "domain");

CREATE TABLE IF NOT EXISTS "Alchemi_FeatureEntitlementTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "domain" TEXT NOT NULL,
  "feature_code" TEXT NOT NULL,
  "scope_type" TEXT NOT NULL,
  "scope_id" TEXT NOT NULL,
  "enabled" BOOLEAN NOT NULL DEFAULT TRUE,
  "config_json" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_FeatureEntitlementTable_scope_feature_key" ON "Alchemi_FeatureEntitlementTable"("account_id", "domain", "feature_code", "scope_type", "scope_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotMarketplaceTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "entity_type" TEXT NOT NULL,
  "entity_id" TEXT NOT NULL,
  "title" TEXT NOT NULL,
  "description" TEXT,
  "is_published" BOOLEAN NOT NULL DEFAULT TRUE,
  "is_featured" BOOLEAN NOT NULL DEFAULT FALSE,
  "is_verified" BOOLEAN NOT NULL DEFAULT FALSE,
  "pricing_model" TEXT NOT NULL DEFAULT 'free',
  "version" TEXT NOT NULL DEFAULT '1.0.0',
  "author" TEXT,
  "installation_count" INTEGER NOT NULL DEFAULT 0,
  "rating_avg" DOUBLE PRECISION NOT NULL DEFAULT 0,
  "rating_count" INTEGER NOT NULL DEFAULT 0,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotMarketplaceTable_account_id_idx" ON "Alchemi_CopilotMarketplaceTable"("account_id");
ALTER TABLE "Alchemi_CopilotMarketplaceTable" ADD COLUMN IF NOT EXISTS "is_featured" BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE "Alchemi_CopilotMarketplaceTable" ADD COLUMN IF NOT EXISTS "is_verified" BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE "Alchemi_CopilotMarketplaceTable" ADD COLUMN IF NOT EXISTS "pricing_model" TEXT NOT NULL DEFAULT 'free';
ALTER TABLE "Alchemi_CopilotMarketplaceTable" ADD COLUMN IF NOT EXISTS "version" TEXT NOT NULL DEFAULT '1.0.0';
ALTER TABLE "Alchemi_CopilotMarketplaceTable" ADD COLUMN IF NOT EXISTS "author" TEXT;
ALTER TABLE "Alchemi_CopilotMarketplaceTable" ADD COLUMN IF NOT EXISTS "installation_count" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "Alchemi_CopilotMarketplaceTable" ADD COLUMN IF NOT EXISTS "rating_avg" DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE "Alchemi_CopilotMarketplaceTable" ADD COLUMN IF NOT EXISTS "rating_count" INTEGER NOT NULL DEFAULT 0;
ALTER TABLE "Alchemi_CopilotMarketplaceTable" ADD COLUMN IF NOT EXISTS "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotMarketplaceGrantTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "marketplace_id" TEXT NOT NULL,
  "scope_type" TEXT NOT NULL,
  "scope_id" TEXT NOT NULL,
  "created_by" TEXT,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotMarketplaceGrantTable_account_id_idx" ON "Alchemi_CopilotMarketplaceGrantTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotMarketplaceGrantTable_marketplace_id_idx" ON "Alchemi_CopilotMarketplaceGrantTable"("marketplace_id");
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CopilotMarketplaceGrantTable_scope_key"
  ON "Alchemi_CopilotMarketplaceGrantTable"("marketplace_id", "scope_type", "scope_id");

CREATE TABLE IF NOT EXISTS "Alchemi_CopilotUsageLedgerTable" (
  "id" TEXT PRIMARY KEY,
  "account_id" TEXT NOT NULL,
  "org_id" TEXT,
  "team_id" TEXT,
  "user_id" TEXT,
  "agent_id" TEXT,
  "model_name" TEXT,
  "connection_id" TEXT,
  "guardrail_code" TEXT,
  "raw_cost" DOUBLE PRECISION NOT NULL DEFAULT 0,
  "credit_factor" DOUBLE PRECISION NOT NULL DEFAULT 1,
  "credits_incurred" DOUBLE PRECISION NOT NULL DEFAULT 0,
  "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS "Alchemi_CopilotUsageLedgerTable_account_id_idx" ON "Alchemi_CopilotUsageLedgerTable"("account_id");
