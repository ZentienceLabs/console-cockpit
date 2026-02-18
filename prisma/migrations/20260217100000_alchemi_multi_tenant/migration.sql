-- Alchemi Multi-Tenant Schema Migration
-- Adds account_id column to all existing tables and creates Alchemi tenant tables
-- Index names use Prisma convention: <Table>_account_id_idx

-- Add account_id to existing tables (safe: IF NOT EXISTS via DO blocks)

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_BudgetTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_BudgetTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_BudgetTable_account_id_idx" ON "LiteLLM_BudgetTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_CredentialsTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_CredentialsTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_CredentialsTable_account_id_idx" ON "LiteLLM_CredentialsTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_ProxyModelTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_ProxyModelTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_ProxyModelTable_account_id_idx" ON "LiteLLM_ProxyModelTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_Config' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_Config" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_Config_account_id_idx" ON "LiteLLM_Config"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_OrganizationTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_OrganizationTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_OrganizationTable_account_id_idx" ON "LiteLLM_OrganizationTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_TeamTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_TeamTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_TeamTable_account_id_idx" ON "LiteLLM_TeamTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_UserTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_UserTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_UserTable_account_id_idx" ON "LiteLLM_UserTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_VerificationToken' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_VerificationToken" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_VerificationToken_account_id_idx" ON "LiteLLM_VerificationToken"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_SpendLogs' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_SpendLogs" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_SpendLogs_account_id_idx" ON "LiteLLM_SpendLogs"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_AuditLog' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_AuditLog" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_AuditLog_account_id_idx" ON "LiteLLM_AuditLog"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_ErrorLogs' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_ErrorLogs" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_ErrorLogs_account_id_idx" ON "LiteLLM_ErrorLogs"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_AgentsTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_AgentsTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_AgentsTable_account_id_idx" ON "LiteLLM_AgentsTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_MCPServerTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_MCPServerTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_MCPServerTable_account_id_idx" ON "LiteLLM_MCPServerTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_GuardrailsTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_GuardrailsTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_GuardrailsTable_account_id_idx" ON "LiteLLM_GuardrailsTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_PolicyTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_PolicyTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_PolicyTable_account_id_idx" ON "LiteLLM_PolicyTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_PolicyAttachmentTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_PolicyAttachmentTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_PolicyAttachmentTable_account_id_idx" ON "LiteLLM_PolicyAttachmentTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_AccessGroupTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_AccessGroupTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_AccessGroupTable_account_id_idx" ON "LiteLLM_AccessGroupTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_DailyUserSpend' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_DailyUserSpend" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_DailyUserSpend_account_id_idx" ON "LiteLLM_DailyUserSpend"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_DailyTeamSpend' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_DailyTeamSpend" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_DailyTeamSpend_account_id_idx" ON "LiteLLM_DailyTeamSpend"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_DailyOrganizationSpend' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_DailyOrganizationSpend" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_DailyOrganizationSpend_account_id_idx" ON "LiteLLM_DailyOrganizationSpend"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_DailyEndUserSpend' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_DailyEndUserSpend" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_DailyEndUserSpend_account_id_idx" ON "LiteLLM_DailyEndUserSpend"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_DailyAgentSpend' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_DailyAgentSpend" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_DailyAgentSpend_account_id_idx" ON "LiteLLM_DailyAgentSpend"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_DailyTagSpend' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_DailyTagSpend" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_DailyTagSpend_account_id_idx" ON "LiteLLM_DailyTagSpend"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_TagTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_TagTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_TagTable_account_id_idx" ON "LiteLLM_TagTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_EndUserTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_EndUserTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_EndUserTable_account_id_idx" ON "LiteLLM_EndUserTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_InvitationLink' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_InvitationLink" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_InvitationLink_account_id_idx" ON "LiteLLM_InvitationLink"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_TeamMembership' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_TeamMembership" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_OrganizationMembership' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_OrganizationMembership" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_ObjectPermissionTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_ObjectPermissionTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_DeletedTeamTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_DeletedTeamTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_DeletedTeamTable_account_id_idx" ON "LiteLLM_DeletedTeamTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_DeletedVerificationToken' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_DeletedVerificationToken" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_DeletedVerificationToken_account_id_idx" ON "LiteLLM_DeletedVerificationToken"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_HealthCheckTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_HealthCheckTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_HealthCheckTable_account_id_idx" ON "LiteLLM_HealthCheckTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_PromptTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_PromptTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_PromptTable_account_id_idx" ON "LiteLLM_PromptTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_SearchToolsTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_SearchToolsTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_SearchToolsTable_account_id_idx" ON "LiteLLM_SearchToolsTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_SkillsTable' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_SkillsTable" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS "LiteLLM_SkillsTable_account_id_idx" ON "LiteLLM_SkillsTable"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_SSOConfig' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_SSOConfig" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_CacheConfig' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_CacheConfig" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='LiteLLM_UISettings' AND column_name='account_id') THEN
    ALTER TABLE "LiteLLM_UISettings" ADD COLUMN "account_id" TEXT;
  END IF;
END $$;

-- Create Alchemi tenant tables

CREATE TABLE IF NOT EXISTS "Alchemi_AccountTable" (
    "account_id" TEXT NOT NULL,
    "account_name" TEXT NOT NULL,
    "account_alias" TEXT,
    "domain" TEXT,
    "status" TEXT NOT NULL DEFAULT 'active',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "max_budget" DOUBLE PRECISION,
    "spend" DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AccountTable_pkey" PRIMARY KEY ("account_id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccountTable_account_name_key" ON "Alchemi_AccountTable"("account_name");
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccountTable_domain_key" ON "Alchemi_AccountTable"("domain");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountTable_domain_idx" ON "Alchemi_AccountTable"("domain");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountTable_status_idx" ON "Alchemi_AccountTable"("status");

CREATE TABLE IF NOT EXISTS "Alchemi_AccountAdminTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT NOT NULL,
    "user_email" TEXT NOT NULL,
    "role" TEXT NOT NULL DEFAULT 'account_admin',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "created_by" TEXT,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AccountAdminTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccountAdminTable_account_id_user_email_key" ON "Alchemi_AccountAdminTable"("account_id", "user_email");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountAdminTable_user_email_idx" ON "Alchemi_AccountAdminTable"("user_email");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_AccountAdminTable_account_id_fkey') THEN
    ALTER TABLE "Alchemi_AccountAdminTable" ADD CONSTRAINT "Alchemi_AccountAdminTable_account_id_fkey"
      FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id") ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_AccountSSOConfig" (
    "id" TEXT NOT NULL,
    "account_id" TEXT NOT NULL,
    "sso_provider" TEXT,
    "sso_settings" JSONB NOT NULL DEFAULT '{}',
    "enabled" BOOLEAN NOT NULL DEFAULT false,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AccountSSOConfig_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccountSSOConfig_account_id_key" ON "Alchemi_AccountSSOConfig"("account_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_AccountSSOConfig_account_id_fkey') THEN
    ALTER TABLE "Alchemi_AccountSSOConfig" ADD CONSTRAINT "Alchemi_AccountSSOConfig_account_id_fkey"
      FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id") ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END $$;

-- FK from OrganizationTable to AccountTable
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='LiteLLM_OrganizationTable_account_id_fkey') THEN
    ALTER TABLE "LiteLLM_OrganizationTable" ADD CONSTRAINT "LiteLLM_OrganizationTable_account_id_fkey"
      FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;
