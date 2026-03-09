-- Alchemi Control Plane Phase 1
-- Adds canonical control-plane tables for shared identity, memberships,
-- groups/teams, role bindings, product grants, and Zitadel identity bindings.

CREATE TABLE IF NOT EXISTS "Alchemi_ControlPlaneUserTable" (
  "user_id" TEXT NOT NULL,
  "user_email" TEXT NOT NULL,
  "display_name" TEXT,
  "zitadel_sub" TEXT,
  "status" TEXT NOT NULL DEFAULT 'active',
  "primary_account_id" TEXT,
  "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "created_by" TEXT,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_by" TEXT,
  CONSTRAINT "Alchemi_ControlPlaneUserTable_pkey" PRIMARY KEY ("user_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_ControlPlaneUserTable_user_email_key"
ON "Alchemi_ControlPlaneUserTable"("user_email");

CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_ControlPlaneUserTable_zitadel_sub_key"
ON "Alchemi_ControlPlaneUserTable"("zitadel_sub");

CREATE INDEX IF NOT EXISTS "Alchemi_ControlPlaneUserTable_primary_account_id_idx"
ON "Alchemi_ControlPlaneUserTable"("primary_account_id");

CREATE INDEX IF NOT EXISTS "Alchemi_ControlPlaneUserTable_status_idx"
ON "Alchemi_ControlPlaneUserTable"("status");

CREATE TABLE IF NOT EXISTS "Alchemi_AccountMembershipTable" (
  "membership_id" TEXT NOT NULL,
  "account_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "membership_role" TEXT NOT NULL DEFAULT 'member',
  "membership_status" TEXT NOT NULL DEFAULT 'active',
  "is_default" BOOLEAN NOT NULL DEFAULT false,
  "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "created_by" TEXT,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_by" TEXT,
  CONSTRAINT "Alchemi_AccountMembershipTable_pkey" PRIMARY KEY ("membership_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_AccountMembershipTable_account_id_user_id_key"
ON "Alchemi_AccountMembershipTable"("account_id", "user_id");

CREATE INDEX IF NOT EXISTS "Alchemi_AccountMembershipTable_account_id_idx"
ON "Alchemi_AccountMembershipTable"("account_id");

CREATE INDEX IF NOT EXISTS "Alchemi_AccountMembershipTable_user_id_idx"
ON "Alchemi_AccountMembershipTable"("user_id");

CREATE INDEX IF NOT EXISTS "Alchemi_AccountMembershipTable_membership_status_idx"
ON "Alchemi_AccountMembershipTable"("membership_status");

CREATE TABLE IF NOT EXISTS "Alchemi_ControlPlaneGroupTable" (
  "group_id" TEXT NOT NULL,
  "account_id" TEXT NOT NULL,
  "group_name" TEXT NOT NULL,
  "group_slug" TEXT,
  "group_kind" TEXT NOT NULL DEFAULT 'org',
  "parent_group_id" TEXT,
  "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "created_by" TEXT,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_by" TEXT,
  CONSTRAINT "Alchemi_ControlPlaneGroupTable_pkey" PRIMARY KEY ("group_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_ControlPlaneGroupTable_account_id_group_name_key"
ON "Alchemi_ControlPlaneGroupTable"("account_id", "group_name");

CREATE INDEX IF NOT EXISTS "Alchemi_ControlPlaneGroupTable_account_id_idx"
ON "Alchemi_ControlPlaneGroupTable"("account_id");

CREATE INDEX IF NOT EXISTS "Alchemi_ControlPlaneGroupTable_group_kind_idx"
ON "Alchemi_ControlPlaneGroupTable"("group_kind");

CREATE INDEX IF NOT EXISTS "Alchemi_ControlPlaneGroupTable_parent_group_id_idx"
ON "Alchemi_ControlPlaneGroupTable"("parent_group_id");

CREATE TABLE IF NOT EXISTS "Alchemi_ControlPlaneTeamTable" (
  "team_id" TEXT NOT NULL,
  "account_id" TEXT NOT NULL,
  "group_id" TEXT,
  "team_name" TEXT NOT NULL,
  "team_slug" TEXT,
  "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "created_by" TEXT,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_by" TEXT,
  CONSTRAINT "Alchemi_ControlPlaneTeamTable_pkey" PRIMARY KEY ("team_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_ControlPlaneTeamTable_account_id_team_name_key"
ON "Alchemi_ControlPlaneTeamTable"("account_id", "team_name");

CREATE INDEX IF NOT EXISTS "Alchemi_ControlPlaneTeamTable_account_id_idx"
ON "Alchemi_ControlPlaneTeamTable"("account_id");

CREATE INDEX IF NOT EXISTS "Alchemi_ControlPlaneTeamTable_group_id_idx"
ON "Alchemi_ControlPlaneTeamTable"("group_id");

CREATE TABLE IF NOT EXISTS "Alchemi_RoleBindingTable" (
  "role_binding_id" TEXT NOT NULL,
  "account_id" TEXT NOT NULL,
  "principal_type" TEXT NOT NULL,
  "principal_id" TEXT NOT NULL,
  "scope_type" TEXT NOT NULL DEFAULT 'account',
  "scope_id" TEXT,
  "product_code" TEXT,
  "role_code" TEXT NOT NULL,
  "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "created_by" TEXT,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_by" TEXT,
  CONSTRAINT "Alchemi_RoleBindingTable_pkey" PRIMARY KEY ("role_binding_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_RoleBindingTable_unique_binding"
ON "Alchemi_RoleBindingTable"(
  "account_id",
  "principal_type",
  "principal_id",
  "scope_type",
  "role_code",
  COALESCE("product_code", '')
);

CREATE INDEX IF NOT EXISTS "Alchemi_RoleBindingTable_account_id_idx"
ON "Alchemi_RoleBindingTable"("account_id");

CREATE INDEX IF NOT EXISTS "Alchemi_RoleBindingTable_principal_idx"
ON "Alchemi_RoleBindingTable"("principal_type", "principal_id");

CREATE INDEX IF NOT EXISTS "Alchemi_RoleBindingTable_scope_idx"
ON "Alchemi_RoleBindingTable"("scope_type", "scope_id");

CREATE INDEX IF NOT EXISTS "Alchemi_RoleBindingTable_product_code_idx"
ON "Alchemi_RoleBindingTable"("product_code");

CREATE TABLE IF NOT EXISTS "Alchemi_ProductGrantTable" (
  "product_grant_id" TEXT NOT NULL,
  "account_id" TEXT NOT NULL,
  "user_id" TEXT NOT NULL,
  "product_code" TEXT NOT NULL,
  "grant_status" TEXT NOT NULL DEFAULT 'active',
  "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "created_by" TEXT,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_by" TEXT,
  CONSTRAINT "Alchemi_ProductGrantTable_pkey" PRIMARY KEY ("product_grant_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_ProductGrantTable_account_id_user_id_product_code_key"
ON "Alchemi_ProductGrantTable"("account_id", "user_id", "product_code");

CREATE INDEX IF NOT EXISTS "Alchemi_ProductGrantTable_account_id_idx"
ON "Alchemi_ProductGrantTable"("account_id");

CREATE INDEX IF NOT EXISTS "Alchemi_ProductGrantTable_user_id_idx"
ON "Alchemi_ProductGrantTable"("user_id");

CREATE INDEX IF NOT EXISTS "Alchemi_ProductGrantTable_grant_status_idx"
ON "Alchemi_ProductGrantTable"("grant_status");

CREATE TABLE IF NOT EXISTS "Alchemi_IdentityBindingTable" (
  "identity_binding_id" TEXT NOT NULL,
  "account_id" TEXT NOT NULL,
  "provider" TEXT NOT NULL DEFAULT 'zitadel',
  "zitadel_org_id" TEXT,
  "issuer_url" TEXT,
  "client_id" TEXT,
  "default_redirect_url" TEXT,
  "sso_enabled" BOOLEAN NOT NULL DEFAULT false,
  "config" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "metadata" JSONB NOT NULL DEFAULT '{}'::jsonb,
  "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "created_by" TEXT,
  "updated_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updated_by" TEXT,
  CONSTRAINT "Alchemi_IdentityBindingTable_pkey" PRIMARY KEY ("identity_binding_id")
);

CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_IdentityBindingTable_account_id_key"
ON "Alchemi_IdentityBindingTable"("account_id");

CREATE UNIQUE INDEX IF NOT EXISTS "Alchemi_IdentityBindingTable_zitadel_org_id_key"
ON "Alchemi_IdentityBindingTable"("zitadel_org_id");

CREATE INDEX IF NOT EXISTS "Alchemi_IdentityBindingTable_provider_idx"
ON "Alchemi_IdentityBindingTable"("provider");

CREATE INDEX IF NOT EXISTS "Alchemi_IdentityBindingTable_sso_enabled_idx"
ON "Alchemi_IdentityBindingTable"("sso_enabled");

DO $$ BEGIN
  ALTER TABLE "Alchemi_AccountMembershipTable"
  ADD CONSTRAINT "Alchemi_AccountMembershipTable_account_id_fkey"
  FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id")
  ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE "Alchemi_AccountMembershipTable"
  ADD CONSTRAINT "Alchemi_AccountMembershipTable_user_id_fkey"
  FOREIGN KEY ("user_id") REFERENCES "Alchemi_ControlPlaneUserTable"("user_id")
  ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE "Alchemi_ControlPlaneGroupTable"
  ADD CONSTRAINT "Alchemi_ControlPlaneGroupTable_account_id_fkey"
  FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id")
  ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE "Alchemi_ControlPlaneTeamTable"
  ADD CONSTRAINT "Alchemi_ControlPlaneTeamTable_account_id_fkey"
  FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id")
  ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE "Alchemi_ControlPlaneTeamTable"
  ADD CONSTRAINT "Alchemi_ControlPlaneTeamTable_group_id_fkey"
  FOREIGN KEY ("group_id") REFERENCES "Alchemi_ControlPlaneGroupTable"("group_id")
  ON DELETE SET NULL ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE "Alchemi_RoleBindingTable"
  ADD CONSTRAINT "Alchemi_RoleBindingTable_account_id_fkey"
  FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id")
  ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE "Alchemi_ProductGrantTable"
  ADD CONSTRAINT "Alchemi_ProductGrantTable_account_id_fkey"
  FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id")
  ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE "Alchemi_ProductGrantTable"
  ADD CONSTRAINT "Alchemi_ProductGrantTable_user_id_fkey"
  FOREIGN KEY ("user_id") REFERENCES "Alchemi_ControlPlaneUserTable"("user_id")
  ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  ALTER TABLE "Alchemi_IdentityBindingTable"
  ADD CONSTRAINT "Alchemi_IdentityBindingTable_account_id_fkey"
  FOREIGN KEY ("account_id") REFERENCES "Alchemi_AccountTable"("account_id")
  ON DELETE CASCADE ON UPDATE CASCADE;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;
