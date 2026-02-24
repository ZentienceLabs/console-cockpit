-- Migration: add_auth_org_id
-- Adds a functional index on Alchemi_AccountTable.metadata->>'auth_org_id'
-- for fast lookup of accounts by Zitadel organization ID.

CREATE INDEX IF NOT EXISTS "Alchemi_AccountTable_auth_org_id_idx"
ON "Alchemi_AccountTable" ((metadata->>'auth_org_id'))
WHERE metadata->>'auth_org_id' IS NOT NULL;
