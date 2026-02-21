-- Alchemi Centralized Platform Migration
-- Centralizes management tables from alchemi-web and alchemi-ai into console-cockpit
-- All statements are idempotent (safe to re-run)

-- ============================================
-- Group 1: Subscriptions & Plans
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_SubscriptionPlanTable" (
    "id" TEXT NOT NULL,
    "plan_name" TEXT NOT NULL,
    "display_name" TEXT,
    "description" TEXT,
    "price_monthly" DOUBLE PRECISION,
    "price_yearly" DOUBLE PRECISION,
    "currency" TEXT NOT NULL DEFAULT 'USD',
    "features" JSONB NOT NULL DEFAULT '{}',
    "limits" JSONB NOT NULL DEFAULT '{}',
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_SubscriptionPlanTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_SubscriptionPlanTable_is_active_idx" ON "Alchemi_SubscriptionPlanTable"("is_active");
CREATE INDEX IF NOT EXISTS "Alchemi_SubscriptionPlanTable_plan_name_idx" ON "Alchemi_SubscriptionPlanTable"("plan_name");

CREATE TABLE IF NOT EXISTS "Alchemi_SubscriptionTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "plan_id" TEXT NOT NULL,
    "system_subscription_id" TEXT,
    "quantity" INTEGER NOT NULL DEFAULT 1,
    "start_date" TIMESTAMP(3) NOT NULL,
    "end_date" TIMESTAMP(3),
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "razorpay_response" JSONB,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_SubscriptionTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_SubscriptionTable_account_id_idx" ON "Alchemi_SubscriptionTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_SubscriptionTable_plan_id_idx" ON "Alchemi_SubscriptionTable"("plan_id");
CREATE INDEX IF NOT EXISTS "Alchemi_SubscriptionTable_is_active_idx" ON "Alchemi_SubscriptionTable"("is_active");
CREATE INDEX IF NOT EXISTS "Alchemi_SubscriptionTable_system_subscription_id_idx" ON "Alchemi_SubscriptionTable"("system_subscription_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_SubscriptionTable_account_id_fkey') THEN
    ALTER TABLE "Alchemi_SubscriptionTable" ADD CONSTRAINT "Alchemi_SubscriptionTable_account_id_fkey"
      FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_SubscriptionTable_plan_id_fkey') THEN
    ALTER TABLE "Alchemi_SubscriptionTable" ADD CONSTRAINT "Alchemi_SubscriptionTable_plan_id_fkey"
      FOREIGN KEY ("plan_id") REFERENCES "Alchemi_SubscriptionPlanTable"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END $$;

-- ============================================
-- Group 2: Account Membership & Quotas
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_AccountMembershipTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "user_id" TEXT NOT NULL,
    "app_role" TEXT NOT NULL DEFAULT 'member',
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "joined_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "invited_by" TEXT,
    "last_active_at" TIMESTAMP(3),
    "team_id" TEXT,
    "tenant_preferences" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AccountMembershipTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccountMembershipTable_account_id_user_id_key" ON "Alchemi_AccountMembershipTable"("account_id", "user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountMembershipTable_account_id_idx" ON "Alchemi_AccountMembershipTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountMembershipTable_user_id_idx" ON "Alchemi_AccountMembershipTable"("user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountMembershipTable_team_id_idx" ON "Alchemi_AccountMembershipTable"("team_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountMembershipTable_is_active_idx" ON "Alchemi_AccountMembershipTable"("is_active");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_AccountMembershipTable_account_id_fkey') THEN
    ALTER TABLE "Alchemi_AccountMembershipTable" ADD CONSTRAINT "Alchemi_AccountMembershipTable_account_id_fkey"
      FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_AccountQuotaTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "subscription_id" TEXT,
    "product_code" TEXT,
    "feature_code" TEXT,
    "unit" TEXT NOT NULL DEFAULT 'credits',
    "included" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "used" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "overage_used" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "overage_limit" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "reset_policy" TEXT NOT NULL DEFAULT 'MONTHLY',
    "rollover_enabled" BOOLEAN NOT NULL DEFAULT false,
    "rollover_cap" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "rollover_from_previous" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "period_start" TIMESTAMP(3) NOT NULL,
    "period_end" TIMESTAMP(3) NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AccountQuotaTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_AccountQuotaTable_account_id_idx" ON "Alchemi_AccountQuotaTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountQuotaTable_subscription_id_idx" ON "Alchemi_AccountQuotaTable"("subscription_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountQuotaTable_unit_idx" ON "Alchemi_AccountQuotaTable"("unit");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountQuotaTable_product_code_idx" ON "Alchemi_AccountQuotaTable"("product_code");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountQuotaTable_is_active_idx" ON "Alchemi_AccountQuotaTable"("is_active");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountQuotaTable_account_id_unit_is_active_idx" ON "Alchemi_AccountQuotaTable"("account_id", "unit", "is_active");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_AccountQuotaTable_subscription_id_fkey') THEN
    ALTER TABLE "Alchemi_AccountQuotaTable" ADD CONSTRAINT "Alchemi_AccountQuotaTable_subscription_id_fkey"
      FOREIGN KEY ("subscription_id") REFERENCES "Alchemi_SubscriptionTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

-- ============================================
-- Group 3: Roles & Permissions (CASL)
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_RoleTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "name" TEXT NOT NULL,
    "type" TEXT,
    "provider" TEXT NOT NULL DEFAULT 'PLATFORM',
    "is_default" BOOLEAN NOT NULL DEFAULT false,
    "is_deleted" BOOLEAN NOT NULL DEFAULT false,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_RoleTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_RoleTable_account_id_name_key" ON "Alchemi_RoleTable"("account_id", "name");
CREATE INDEX IF NOT EXISTS "Alchemi_RoleTable_account_id_idx" ON "Alchemi_RoleTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_RoleTable_provider_idx" ON "Alchemi_RoleTable"("provider");
CREATE INDEX IF NOT EXISTS "Alchemi_RoleTable_is_default_idx" ON "Alchemi_RoleTable"("is_default");

CREATE TABLE IF NOT EXISTS "Alchemi_PermissionTable" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "subject" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "is_system_permission" BOOLEAN NOT NULL DEFAULT false,
    "fields" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "conditions" TEXT,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_PermissionTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_PermissionTable_subject_idx" ON "Alchemi_PermissionTable"("subject");
CREATE INDEX IF NOT EXISTS "Alchemi_PermissionTable_action_idx" ON "Alchemi_PermissionTable"("action");
CREATE INDEX IF NOT EXISTS "Alchemi_PermissionTable_name_idx" ON "Alchemi_PermissionTable"("name");
CREATE INDEX IF NOT EXISTS "Alchemi_PermissionTable_subject_action_idx" ON "Alchemi_PermissionTable"("subject", "action");

CREATE TABLE IF NOT EXISTS "Alchemi_RolePermissionTable" (
    "id" TEXT NOT NULL,
    "role_id" TEXT NOT NULL,
    "permission_id" TEXT NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_RolePermissionTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_RolePermissionTable_role_id_permission_id_key" ON "Alchemi_RolePermissionTable"("role_id", "permission_id");
CREATE INDEX IF NOT EXISTS "Alchemi_RolePermissionTable_role_id_idx" ON "Alchemi_RolePermissionTable"("role_id");
CREATE INDEX IF NOT EXISTS "Alchemi_RolePermissionTable_permission_id_idx" ON "Alchemi_RolePermissionTable"("permission_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_RolePermissionTable_role_id_fkey') THEN
    ALTER TABLE "Alchemi_RolePermissionTable" ADD CONSTRAINT "Alchemi_RolePermissionTable_role_id_fkey"
      FOREIGN KEY ("role_id") REFERENCES "Alchemi_RoleTable"("id") ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_RolePermissionTable_permission_id_fkey') THEN
    ALTER TABLE "Alchemi_RolePermissionTable" ADD CONSTRAINT "Alchemi_RolePermissionTable_permission_id_fkey"
      FOREIGN KEY ("permission_id") REFERENCES "Alchemi_PermissionTable"("id") ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

-- ============================================
-- Group 4: Workspaces
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_WorkspaceTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "current_analysis_state" TEXT,
    "is_mvp_ready" BOOLEAN NOT NULL DEFAULT false,
    "product_info" JSONB NOT NULL DEFAULT '{}',
    "workspace_info" JSONB NOT NULL DEFAULT '{}',
    "analysis_data" JSONB NOT NULL DEFAULT '{}',
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_WorkspaceTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_WorkspaceTable_account_id_idx" ON "Alchemi_WorkspaceTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_WorkspaceTable_name_idx" ON "Alchemi_WorkspaceTable"("name");
CREATE INDEX IF NOT EXISTS "Alchemi_WorkspaceTable_status_idx" ON "Alchemi_WorkspaceTable"("status");

CREATE TABLE IF NOT EXISTS "Alchemi_WorkspaceMemberTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "workspace_id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "role_id" TEXT,
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_WorkspaceMemberTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_WorkspaceMemberTable_workspace_id_user_id_key" ON "Alchemi_WorkspaceMemberTable"("workspace_id", "user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_WorkspaceMemberTable_account_id_idx" ON "Alchemi_WorkspaceMemberTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_WorkspaceMemberTable_user_id_idx" ON "Alchemi_WorkspaceMemberTable"("user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_WorkspaceMemberTable_workspace_id_idx" ON "Alchemi_WorkspaceMemberTable"("workspace_id");
CREATE INDEX IF NOT EXISTS "Alchemi_WorkspaceMemberTable_role_id_idx" ON "Alchemi_WorkspaceMemberTable"("role_id");
CREATE INDEX IF NOT EXISTS "Alchemi_WorkspaceMemberTable_status_idx" ON "Alchemi_WorkspaceMemberTable"("status");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_WorkspaceMemberTable_workspace_id_fkey') THEN
    ALTER TABLE "Alchemi_WorkspaceMemberTable" ADD CONSTRAINT "Alchemi_WorkspaceMemberTable_workspace_id_fkey"
      FOREIGN KEY ("workspace_id") REFERENCES "Alchemi_WorkspaceTable"("id") ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_WorkspaceMemberTable_role_id_fkey') THEN
    ALTER TABLE "Alchemi_WorkspaceMemberTable" ADD CONSTRAINT "Alchemi_WorkspaceMemberTable_role_id_fkey"
      FOREIGN KEY ("role_id") REFERENCES "Alchemi_RoleTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

-- ============================================
-- Group 5: Agent Registry
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_AgentDefTable" (
    "agent_id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "prompt" TEXT,
    "page" TEXT,
    "categories" JSONB NOT NULL DEFAULT '{}',
    "tags" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "builtin_tools" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "tools_mcp_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "tools_openapi_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "links" JSONB NOT NULL DEFAULT '{}',
    "is_singleton" BOOLEAN NOT NULL DEFAULT false,
    "is_non_conversational" BOOLEAN NOT NULL DEFAULT false,
    "status" TEXT NOT NULL DEFAULT 'active',
    "availability" TEXT[] DEFAULT ARRAY['platform']::TEXT[],
    "provider" TEXT NOT NULL DEFAULT 'PLATFORM',
    "account_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AgentDefTable_pkey" PRIMARY KEY ("agent_id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_AgentDefTable_account_id_idx" ON "Alchemi_AgentDefTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentDefTable_name_idx" ON "Alchemi_AgentDefTable"("name");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentDefTable_page_idx" ON "Alchemi_AgentDefTable"("page");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentDefTable_status_idx" ON "Alchemi_AgentDefTable"("status");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentDefTable_provider_idx" ON "Alchemi_AgentDefTable"("provider");

CREATE TABLE IF NOT EXISTS "Alchemi_AgentGroupTable" (
    "id" TEXT NOT NULL,
    "group_code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "group_type" TEXT NOT NULL,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "status" TEXT NOT NULL DEFAULT 'active',
    "account_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AgentGroupTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AgentGroupTable_group_code_key" ON "Alchemi_AgentGroupTable"("group_code");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentGroupTable_account_id_idx" ON "Alchemi_AgentGroupTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentGroupTable_group_code_idx" ON "Alchemi_AgentGroupTable"("group_code");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentGroupTable_group_type_idx" ON "Alchemi_AgentGroupTable"("group_type");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentGroupTable_status_idx" ON "Alchemi_AgentGroupTable"("status");

CREATE TABLE IF NOT EXISTS "Alchemi_AgentGroupMemberTable" (
    "id" TEXT NOT NULL,
    "group_id" TEXT NOT NULL,
    "agent_id" TEXT NOT NULL,
    "display_order" INTEGER NOT NULL DEFAULT 0,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "account_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AgentGroupMemberTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AgentGroupMemberTable_group_id_agent_id_key" ON "Alchemi_AgentGroupMemberTable"("group_id", "agent_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentGroupMemberTable_account_id_idx" ON "Alchemi_AgentGroupMemberTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentGroupMemberTable_group_id_idx" ON "Alchemi_AgentGroupMemberTable"("group_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentGroupMemberTable_agent_id_idx" ON "Alchemi_AgentGroupMemberTable"("agent_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_AgentGroupMemberTable_group_id_fkey') THEN
    ALTER TABLE "Alchemi_AgentGroupMemberTable" ADD CONSTRAINT "Alchemi_AgentGroupMemberTable_group_id_fkey"
      FOREIGN KEY ("group_id") REFERENCES "Alchemi_AgentGroupTable"("id") ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_AgentGroupMemberTable_agent_id_fkey') THEN
    ALTER TABLE "Alchemi_AgentGroupMemberTable" ADD CONSTRAINT "Alchemi_AgentGroupMemberTable_agent_id_fkey"
      FOREIGN KEY ("agent_id") REFERENCES "Alchemi_AgentDefTable"("agent_id") ON DELETE CASCADE ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_AgentMarketplaceTable" (
    "id" TEXT NOT NULL,
    "agent_id" TEXT NOT NULL,
    "listing_status" TEXT NOT NULL DEFAULT 'draft',
    "listing_data" JSONB NOT NULL DEFAULT '{}',
    "account_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AgentMarketplaceTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_AgentMarketplaceTable_account_id_idx" ON "Alchemi_AgentMarketplaceTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentMarketplaceTable_agent_id_idx" ON "Alchemi_AgentMarketplaceTable"("agent_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AgentMarketplaceTable_listing_status_idx" ON "Alchemi_AgentMarketplaceTable"("listing_status");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_AgentMarketplaceTable_agent_id_fkey') THEN
    ALTER TABLE "Alchemi_AgentMarketplaceTable" ADD CONSTRAINT "Alchemi_AgentMarketplaceTable_agent_id_fkey"
      FOREIGN KEY ("agent_id") REFERENCES "Alchemi_AgentDefTable"("agent_id") ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END $$;

-- ============================================
-- Group 6: Guardrails
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_GuardrailsConfigTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "guard_type" TEXT NOT NULL,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "execution_order" INTEGER NOT NULL DEFAULT 1,
    "action_on_fail" TEXT NOT NULL DEFAULT 'block',
    "config" JSONB NOT NULL DEFAULT '{}',
    "version" INTEGER NOT NULL DEFAULT 1,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_GuardrailsConfigTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_GuardrailsConfigTable_account_id_guard_type_key" ON "Alchemi_GuardrailsConfigTable"("account_id", "guard_type");
CREATE INDEX IF NOT EXISTS "Alchemi_GuardrailsConfigTable_account_id_idx" ON "Alchemi_GuardrailsConfigTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_GuardrailsConfigTable_enabled_idx" ON "Alchemi_GuardrailsConfigTable"("enabled");

CREATE TABLE IF NOT EXISTS "Alchemi_GuardrailsCustomPatternTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "guard_type" TEXT NOT NULL,
    "pattern_name" TEXT NOT NULL,
    "pattern" TEXT NOT NULL,
    "description" TEXT,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "created_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_GuardrailsCustomPatternTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_GuardrailsCustomPatternTable_account_id_idx" ON "Alchemi_GuardrailsCustomPatternTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_GuardrailsCustomPatternTable_guard_type_idx" ON "Alchemi_GuardrailsCustomPatternTable"("guard_type");

CREATE TABLE IF NOT EXISTS "Alchemi_GuardrailsAuditLogTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "guard_type" TEXT NOT NULL,
    "action" TEXT NOT NULL,
    "result" TEXT NOT NULL,
    "request_data" JSONB,
    "response_data" JSONB,
    "user_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_GuardrailsAuditLogTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_GuardrailsAuditLogTable_account_id_idx" ON "Alchemi_GuardrailsAuditLogTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_GuardrailsAuditLogTable_guard_type_idx" ON "Alchemi_GuardrailsAuditLogTable"("guard_type");
CREATE INDEX IF NOT EXISTS "Alchemi_GuardrailsAuditLogTable_created_at_idx" ON "Alchemi_GuardrailsAuditLogTable"("created_at");
CREATE INDEX IF NOT EXISTS "Alchemi_GuardrailsAuditLogTable_user_id_idx" ON "Alchemi_GuardrailsAuditLogTable"("user_id");

-- ============================================
-- Group 7: Configuration
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_ConfigProviderTable" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "display_label" TEXT,
    "endpoint_env_var" TEXT,
    "api_key_env_var" TEXT,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "account_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_ConfigProviderTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigProviderTable_account_id_idx" ON "Alchemi_ConfigProviderTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigProviderTable_is_active_idx" ON "Alchemi_ConfigProviderTable"("is_active");

CREATE TABLE IF NOT EXISTS "Alchemi_ConfigModelTable" (
    "id" TEXT NOT NULL,
    "provider_id" TEXT NOT NULL,
    "deployment_name" TEXT NOT NULL,
    "display_name" TEXT,
    "capability" TEXT,
    "input_cost_per_million" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "output_cost_per_million" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "content_capabilities" JSONB NOT NULL DEFAULT '{}',
    "extra_body" JSONB NOT NULL DEFAULT '{}',
    "sort_order" INTEGER NOT NULL DEFAULT 0,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "account_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_ConfigModelTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigModelTable_account_id_idx" ON "Alchemi_ConfigModelTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigModelTable_provider_id_idx" ON "Alchemi_ConfigModelTable"("provider_id");
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigModelTable_is_active_idx" ON "Alchemi_ConfigModelTable"("is_active");
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigModelTable_capability_idx" ON "Alchemi_ConfigModelTable"("capability");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_ConfigModelTable_provider_id_fkey') THEN
    ALTER TABLE "Alchemi_ConfigModelTable" ADD CONSTRAINT "Alchemi_ConfigModelTable_provider_id_fkey"
      FOREIGN KEY ("provider_id") REFERENCES "Alchemi_ConfigProviderTable"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_ConfigDefaultModelTable" (
    "id" TEXT NOT NULL,
    "model_id" TEXT NOT NULL,
    "account_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_ConfigDefaultModelTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigDefaultModelTable_account_id_idx" ON "Alchemi_ConfigDefaultModelTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_ConfigSandboxPricingTable" (
    "id" TEXT NOT NULL,
    "resource_type" TEXT NOT NULL,
    "unit" TEXT NOT NULL,
    "cost_usd" DOUBLE PRECISION NOT NULL,
    "description" TEXT,
    "effective_from" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "effective_to" TIMESTAMP(3),
    "account_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_ConfigSandboxPricingTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigSandboxPricingTable_account_id_idx" ON "Alchemi_ConfigSandboxPricingTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigSandboxPricingTable_resource_type_idx" ON "Alchemi_ConfigSandboxPricingTable"("resource_type");
CREATE INDEX IF NOT EXISTS "Alchemi_ConfigSandboxPricingTable_effective_to_idx" ON "Alchemi_ConfigSandboxPricingTable"("effective_to");

-- ============================================
-- Group 8: Integrations & Connections
-- ============================================

-- Note: Alchemi_ConnectionTable and Alchemi_MvpConfigTable have circular FK.
-- Create both tables first, then add FK constraints.

CREATE TABLE IF NOT EXISTS "Alchemi_MvpConfigTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "workspace_id" TEXT,
    "name" TEXT NOT NULL,
    "description" TEXT DEFAULT '',
    "creation_type" TEXT NOT NULL DEFAULT 'default',
    "mvp_type" TEXT NOT NULL DEFAULT 'simple',
    "framework" TEXT NOT NULL DEFAULT 'nextjs',
    "commit_count" INTEGER NOT NULL DEFAULT 0,
    "connections" JSONB NOT NULL DEFAULT '{}',
    "base_versions" JSONB NOT NULL DEFAULT '[]',
    "config" JSONB NOT NULL DEFAULT '{}',
    "access_token" TEXT,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_MvpConfigTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_MvpConfigTable_account_id_name_key" ON "Alchemi_MvpConfigTable"("account_id", "name");
CREATE INDEX IF NOT EXISTS "Alchemi_MvpConfigTable_account_id_idx" ON "Alchemi_MvpConfigTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_MvpConfigTable_workspace_id_idx" ON "Alchemi_MvpConfigTable"("workspace_id");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_MvpConfigTable_workspace_id_fkey') THEN
    ALTER TABLE "Alchemi_MvpConfigTable" ADD CONSTRAINT "Alchemi_MvpConfigTable_workspace_id_fkey"
      FOREIGN KEY ("workspace_id") REFERENCES "Alchemi_WorkspaceTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_ConnectionTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "workspace_id" TEXT,
    "name" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "config" JSONB NOT NULL DEFAULT '{}',
    "mvp_version_id" TEXT,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_ConnectionTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_ConnectionTable_account_id_idx" ON "Alchemi_ConnectionTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_ConnectionTable_workspace_id_idx" ON "Alchemi_ConnectionTable"("workspace_id");
CREATE INDEX IF NOT EXISTS "Alchemi_ConnectionTable_type_idx" ON "Alchemi_ConnectionTable"("type");
CREATE INDEX IF NOT EXISTS "Alchemi_ConnectionTable_status_idx" ON "Alchemi_ConnectionTable"("status");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_ConnectionTable_workspace_id_fkey') THEN
    ALTER TABLE "Alchemi_ConnectionTable" ADD CONSTRAINT "Alchemi_ConnectionTable_workspace_id_fkey"
      FOREIGN KEY ("workspace_id") REFERENCES "Alchemi_WorkspaceTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_ConnectionTable_mvp_version_id_fkey') THEN
    ALTER TABLE "Alchemi_ConnectionTable" ADD CONSTRAINT "Alchemi_ConnectionTable_mvp_version_id_fkey"
      FOREIGN KEY ("mvp_version_id") REFERENCES "Alchemi_MvpConfigTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_McpConfigTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "workspace_id" TEXT,
    "name" TEXT NOT NULL,
    "server_name" TEXT NOT NULL,
    "config" JSONB NOT NULL DEFAULT '{}',
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "mvp_version_id" TEXT,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_McpConfigTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_McpConfigTable_account_id_idx" ON "Alchemi_McpConfigTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_McpConfigTable_workspace_id_idx" ON "Alchemi_McpConfigTable"("workspace_id");
CREATE INDEX IF NOT EXISTS "Alchemi_McpConfigTable_is_active_idx" ON "Alchemi_McpConfigTable"("is_active");
CREATE INDEX IF NOT EXISTS "Alchemi_McpConfigTable_server_name_idx" ON "Alchemi_McpConfigTable"("server_name");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_McpConfigTable_workspace_id_fkey') THEN
    ALTER TABLE "Alchemi_McpConfigTable" ADD CONSTRAINT "Alchemi_McpConfigTable_workspace_id_fkey"
      FOREIGN KEY ("workspace_id") REFERENCES "Alchemi_WorkspaceTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_McpConfigTable_mvp_version_id_fkey') THEN
    ALTER TABLE "Alchemi_McpConfigTable" ADD CONSTRAINT "Alchemi_McpConfigTable_mvp_version_id_fkey"
      FOREIGN KEY ("mvp_version_id") REFERENCES "Alchemi_MvpConfigTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_IntegrationConnectionTable" (
    "id" TEXT NOT NULL,
    "workspace_id" TEXT NOT NULL,
    "user_id" TEXT,
    "connection_level" TEXT NOT NULL DEFAULT 'WORKSPACE',
    "name" TEXT NOT NULL,
    "description_for_agent" TEXT,
    "integration_type" TEXT NOT NULL,
    "app_name" TEXT NOT NULL,
    "composio_entity_id" TEXT NOT NULL,
    "composio_connected_account_id" TEXT,
    "status" TEXT NOT NULL DEFAULT 'active',
    "connected_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "connected_by_user_id" TEXT NOT NULL,
    "account_id" TEXT,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_IntegrationConnectionTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_IntegrationConnectionTable_ws_app_user_key" ON "Alchemi_IntegrationConnectionTable"("workspace_id", "app_name", "user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_IntegrationConnectionTable_account_id_idx" ON "Alchemi_IntegrationConnectionTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_IntegrationConnectionTable_workspace_id_idx" ON "Alchemi_IntegrationConnectionTable"("workspace_id");
CREATE INDEX IF NOT EXISTS "Alchemi_IntegrationConnectionTable_user_id_idx" ON "Alchemi_IntegrationConnectionTable"("user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_IntegrationConnectionTable_composio_entity_id_idx" ON "Alchemi_IntegrationConnectionTable"("composio_entity_id");
CREATE INDEX IF NOT EXISTS "Alchemi_IntegrationConnectionTable_status_idx" ON "Alchemi_IntegrationConnectionTable"("status");

CREATE TABLE IF NOT EXISTS "Alchemi_IntegrationsDefTable" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "description" TEXT,
    "toolkit" TEXT NOT NULL,
    "auth_config_id" TEXT NOT NULL,
    "icon" TEXT,
    "color" TEXT,
    "bg_color" TEXT,
    "enabled" BOOLEAN NOT NULL DEFAULT true,
    "display_order" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_IntegrationsDefTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_IntegrationsDefTable_toolkit_idx" ON "Alchemi_IntegrationsDefTable"("toolkit");
CREATE INDEX IF NOT EXISTS "Alchemi_IntegrationsDefTable_enabled_idx" ON "Alchemi_IntegrationsDefTable"("enabled");

-- ============================================
-- Group 9: Financial (Budget & Cost)
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_BudgetPlanTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "name" TEXT NOT NULL DEFAULT 'Default Plan',
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "distribution" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_BudgetPlanTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_BudgetPlanTable_account_id_idx" ON "Alchemi_BudgetPlanTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_BudgetPlanTable_is_active_idx" ON "Alchemi_BudgetPlanTable"("is_active");

CREATE TABLE IF NOT EXISTS "Alchemi_CreditBudgetTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "budget_plan_id" TEXT,
    "scope_type" TEXT NOT NULL,
    "scope_id" TEXT NOT NULL,
    "allocated" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "limit_amount" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "overflow_cap" DOUBLE PRECISION,
    "used" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "overflow_used" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "cycle_start" TIMESTAMP(3) NOT NULL,
    "cycle_end" TIMESTAMP(3) NOT NULL,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_CreditBudgetTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_CreditBudgetTable_scope_type_scope_id_cycle_start_key" ON "Alchemi_CreditBudgetTable"("scope_type", "scope_id", "cycle_start");
CREATE INDEX IF NOT EXISTS "Alchemi_CreditBudgetTable_account_id_idx" ON "Alchemi_CreditBudgetTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_CreditBudgetTable_scope_type_scope_id_idx" ON "Alchemi_CreditBudgetTable"("scope_type", "scope_id");
CREATE INDEX IF NOT EXISTS "Alchemi_CreditBudgetTable_cycle_start_cycle_end_idx" ON "Alchemi_CreditBudgetTable"("cycle_start", "cycle_end");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_CreditBudgetTable_budget_plan_id_fkey') THEN
    ALTER TABLE "Alchemi_CreditBudgetTable" ADD CONSTRAINT "Alchemi_CreditBudgetTable_budget_plan_id_fkey"
      FOREIGN KEY ("budget_plan_id") REFERENCES "Alchemi_BudgetPlanTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_CostTrackingTable" (
    "id" SERIAL NOT NULL,
    "workspace_id" TEXT NOT NULL,
    "account_id" TEXT,
    "user_id" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "tool" TEXT NOT NULL,
    "cost" DOUBLE PRECISION NOT NULL,
    "prompt_tokens" INTEGER,
    "completion_tokens" INTEGER,
    "total_tokens" INTEGER,
    "metadata" JSONB,
    "thread_id" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_CostTrackingTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_CostTrackingTable_account_id_idx" ON "Alchemi_CostTrackingTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_CostTrackingTable_workspace_id_idx" ON "Alchemi_CostTrackingTable"("workspace_id");
CREATE INDEX IF NOT EXISTS "Alchemi_CostTrackingTable_user_id_idx" ON "Alchemi_CostTrackingTable"("user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_CostTrackingTable_workspace_id_user_id_idx" ON "Alchemi_CostTrackingTable"("workspace_id", "user_id");
CREATE INDEX IF NOT EXISTS "Alchemi_CostTrackingTable_created_at_idx" ON "Alchemi_CostTrackingTable"("created_at");
CREATE INDEX IF NOT EXISTS "Alchemi_CostTrackingTable_workspace_id_created_at_idx" ON "Alchemi_CostTrackingTable"("workspace_id", "created_at");
CREATE INDEX IF NOT EXISTS "Alchemi_CostTrackingTable_thread_id_idx" ON "Alchemi_CostTrackingTable"("thread_id");

-- ============================================
-- Group 10: Platform Catalog & Override Configs
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_PlatformCatalogTable" (
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "parent_code" TEXT,
    "value_config" JSONB NOT NULL DEFAULT '{}',
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "display_order" INTEGER NOT NULL DEFAULT 0,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_PlatformCatalogTable_pkey" PRIMARY KEY ("code")
);
CREATE INDEX IF NOT EXISTS "Alchemi_PlatformCatalogTable_category_idx" ON "Alchemi_PlatformCatalogTable"("category");
CREATE INDEX IF NOT EXISTS "Alchemi_PlatformCatalogTable_parent_code_idx" ON "Alchemi_PlatformCatalogTable"("parent_code");
CREATE INDEX IF NOT EXISTS "Alchemi_PlatformCatalogTable_is_active_idx" ON "Alchemi_PlatformCatalogTable"("is_active");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_PlatformCatalogTable_parent_code_fkey') THEN
    ALTER TABLE "Alchemi_PlatformCatalogTable" ADD CONSTRAINT "Alchemi_PlatformCatalogTable_parent_code_fkey"
      FOREIGN KEY ("parent_code") REFERENCES "Alchemi_PlatformCatalogTable"("code") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_AccountOverrideConfigTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "product_code" TEXT,
    "feature_code" TEXT,
    "entity_code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "parent_entity_code" TEXT,
    "distribution_kind" TEXT,
    "action" TEXT NOT NULL DEFAULT 'RESTRICT',
    "inherit" BOOLEAN NOT NULL DEFAULT true,
    "value_config" JSONB NOT NULL DEFAULT '{}',
    "scope_type" TEXT NOT NULL DEFAULT 'ACCOUNT',
    "scope_id" TEXT,
    "restriction_json" JSONB,
    "reason" TEXT,
    "valid_from" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "valid_until" TIMESTAMP(3),
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AccountOverrideConfigTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccountOverrideConfigTable_acct_entity_scope_key" ON "Alchemi_AccountOverrideConfigTable"("account_id", "entity_code", "scope_type");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountOverrideConfigTable_account_id_idx" ON "Alchemi_AccountOverrideConfigTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountOverrideConfigTable_entity_code_idx" ON "Alchemi_AccountOverrideConfigTable"("entity_code");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountOverrideConfigTable_category_idx" ON "Alchemi_AccountOverrideConfigTable"("category");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountOverrideConfigTable_scope_type_scope_id_idx" ON "Alchemi_AccountOverrideConfigTable"("scope_type", "scope_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountOverrideConfigTable_valid_from_valid_until_idx" ON "Alchemi_AccountOverrideConfigTable"("valid_from", "valid_until");

-- ============================================
-- Group 11: Communication & Support
-- ============================================

CREATE TABLE IF NOT EXISTS "Alchemi_NotificationTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "recipient_id" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'PENDING',
    "read_at" TIMESTAMP(3),
    "sent_at" TIMESTAMP(3),
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_NotificationTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_NotificationTable_account_id_idx" ON "Alchemi_NotificationTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_NotificationTable_recipient_id_idx" ON "Alchemi_NotificationTable"("recipient_id");
CREATE INDEX IF NOT EXISTS "Alchemi_NotificationTable_account_id_recipient_id_idx" ON "Alchemi_NotificationTable"("account_id", "recipient_id");
CREATE INDEX IF NOT EXISTS "Alchemi_NotificationTable_type_idx" ON "Alchemi_NotificationTable"("type");
CREATE INDEX IF NOT EXISTS "Alchemi_NotificationTable_status_idx" ON "Alchemi_NotificationTable"("status");
CREATE INDEX IF NOT EXISTS "Alchemi_NotificationTable_created_at_idx" ON "Alchemi_NotificationTable"("created_at");

CREATE TABLE IF NOT EXISTS "Alchemi_NotificationTemplateTable" (
    "id" TEXT NOT NULL,
    "template_id" TEXT,
    "title_line" TEXT,
    "template_content" TEXT,
    "event_id" TEXT,
    "type" TEXT,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_NotificationTemplateTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_NotificationTemplateTable_template_id_key" ON "Alchemi_NotificationTemplateTable"("template_id");
CREATE INDEX IF NOT EXISTS "Alchemi_NotificationTemplateTable_event_id_idx" ON "Alchemi_NotificationTemplateTable"("event_id");
CREATE INDEX IF NOT EXISTS "Alchemi_NotificationTemplateTable_type_idx" ON "Alchemi_NotificationTemplateTable"("type");

CREATE TABLE IF NOT EXISTS "Alchemi_AccountNotificationTemplateTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "template_id" TEXT NOT NULL,
    "overrides" JSONB NOT NULL DEFAULT '{}',
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AccountNotificationTemplateTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccountNotificationTemplateTable_acct_tmpl_key" ON "Alchemi_AccountNotificationTemplateTable"("account_id", "template_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccountNotificationTemplateTable_account_id_idx" ON "Alchemi_AccountNotificationTemplateTable"("account_id");

CREATE TABLE IF NOT EXISTS "Alchemi_DiscussionTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "workspace_id" TEXT,
    "type" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "parent_object_type" TEXT,
    "parent_object_id" TEXT,
    "parent_message_id" TEXT,
    "resolved" BOOLEAN NOT NULL DEFAULT false,
    "resolved_at" TIMESTAMP(3),
    "resolved_by" TEXT,
    "mentions" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "attachments" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "reactions" JSONB NOT NULL DEFAULT '[]',
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_DiscussionTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_DiscussionTable_account_id_idx" ON "Alchemi_DiscussionTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_DiscussionTable_workspace_id_idx" ON "Alchemi_DiscussionTable"("workspace_id");
CREATE INDEX IF NOT EXISTS "Alchemi_DiscussionTable_parent_object_type_id_idx" ON "Alchemi_DiscussionTable"("parent_object_type", "parent_object_id");
CREATE INDEX IF NOT EXISTS "Alchemi_DiscussionTable_parent_message_id_idx" ON "Alchemi_DiscussionTable"("parent_message_id");
CREATE INDEX IF NOT EXISTS "Alchemi_DiscussionTable_resolved_idx" ON "Alchemi_DiscussionTable"("resolved");

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_DiscussionTable_workspace_id_fkey') THEN
    ALTER TABLE "Alchemi_DiscussionTable" ADD CONSTRAINT "Alchemi_DiscussionTable_workspace_id_fkey"
      FOREIGN KEY ("workspace_id") REFERENCES "Alchemi_WorkspaceTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints WHERE constraint_name='Alchemi_DiscussionTable_parent_message_id_fkey') THEN
    ALTER TABLE "Alchemi_DiscussionTable" ADD CONSTRAINT "Alchemi_DiscussionTable_parent_message_id_fkey"
      FOREIGN KEY ("parent_message_id") REFERENCES "Alchemi_DiscussionTable"("id") ON DELETE SET NULL ON UPDATE CASCADE;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS "Alchemi_UserInviteTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "workspace_id" TEXT,
    "email" TEXT NOT NULL,
    "role_id" TEXT,
    "status" TEXT NOT NULL DEFAULT 'PENDING',
    "token" TEXT NOT NULL,
    "expires_at" TIMESTAMP(3) NOT NULL,
    "accepted_at" TIMESTAMP(3),
    "accepted_by" TEXT,
    "invitation_data" JSONB NOT NULL DEFAULT '{}',
    "created_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_UserInviteTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_UserInviteTable_token_key" ON "Alchemi_UserInviteTable"("token");
CREATE INDEX IF NOT EXISTS "Alchemi_UserInviteTable_account_id_idx" ON "Alchemi_UserInviteTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_UserInviteTable_workspace_id_idx" ON "Alchemi_UserInviteTable"("workspace_id");
CREATE INDEX IF NOT EXISTS "Alchemi_UserInviteTable_email_idx" ON "Alchemi_UserInviteTable"("email");
CREATE INDEX IF NOT EXISTS "Alchemi_UserInviteTable_status_idx" ON "Alchemi_UserInviteTable"("status");
CREATE INDEX IF NOT EXISTS "Alchemi_UserInviteTable_expires_at_idx" ON "Alchemi_UserInviteTable"("expires_at");

CREATE TABLE IF NOT EXISTS "Alchemi_SupportTicketTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "user_profile_id" TEXT,
    "subject" TEXT NOT NULL,
    "description" TEXT NOT NULL,
    "status" TEXT DEFAULT 'OPEN',
    "priority" TEXT NOT NULL DEFAULT 'MEDIUM',
    "assigned_to" TEXT,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_SupportTicketTable_pkey" PRIMARY KEY ("id")
);
CREATE INDEX IF NOT EXISTS "Alchemi_SupportTicketTable_account_id_idx" ON "Alchemi_SupportTicketTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_SupportTicketTable_user_profile_id_idx" ON "Alchemi_SupportTicketTable"("user_profile_id");
CREATE INDEX IF NOT EXISTS "Alchemi_SupportTicketTable_status_idx" ON "Alchemi_SupportTicketTable"("status");
CREATE INDEX IF NOT EXISTS "Alchemi_SupportTicketTable_priority_idx" ON "Alchemi_SupportTicketTable"("priority");
CREATE INDEX IF NOT EXISTS "Alchemi_SupportTicketTable_assigned_to_idx" ON "Alchemi_SupportTicketTable"("assigned_to");
CREATE INDEX IF NOT EXISTS "Alchemi_SupportTicketTable_account_id_status_idx" ON "Alchemi_SupportTicketTable"("account_id", "status");

CREATE TABLE IF NOT EXISTS "Alchemi_AccessTokenTable" (
    "id" TEXT NOT NULL,
    "account_id" TEXT,
    "name" TEXT NOT NULL,
    "workspace_ids" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "token_hash" TEXT NOT NULL,
    "client_id" TEXT,
    "scopes" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "last_used_at" TIMESTAMP(3),
    "expires_at" TIMESTAMP(3),
    "revoked" BOOLEAN NOT NULL DEFAULT false,
    "created_by" TEXT,
    "updated_by" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Alchemi_AccessTokenTable_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccessTokenTable_token_hash_key" ON "Alchemi_AccessTokenTable"("token_hash");
CREATE INDEX IF NOT EXISTS "Alchemi_AccessTokenTable_account_id_idx" ON "Alchemi_AccessTokenTable"("account_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccessTokenTable_client_id_idx" ON "Alchemi_AccessTokenTable"("client_id");
CREATE INDEX IF NOT EXISTS "Alchemi_AccessTokenTable_revoked_idx" ON "Alchemi_AccessTokenTable"("revoked");
CREATE INDEX IF NOT EXISTS "Alchemi_AccessTokenTable_expires_at_idx" ON "Alchemi_AccessTokenTable"("expires_at");
