"""
Migrate single-source tables from alchemi-web into console-cockpit.

These tables exist ONLY in alchemi-web (no deduplication needed).
Each table is read from the source and inserted into the destination
with ON CONFLICT DO NOTHING for idempotent re-runs.

Tables (24):
   1. subscription_plans           -> Alchemi_SubscriptionPlanTable
   2. subscriptions                -> Alchemi_SubscriptionTable
   3. roles                        -> Alchemi_RoleTable
   4. permissions                  -> Alchemi_PermissionTable
   5. role_permissions             -> Alchemi_RolePermissionTable
   6. account_memberships          -> Alchemi_AccountMembershipTable
   7. workspaces                   -> Alchemi_WorkspaceTable
   8. workspace_members            -> Alchemi_WorkspaceMemberTable
   9. guardrails_config            -> Alchemi_GuardrailsConfigTable
  10. guardrails_custom_patterns   -> Alchemi_GuardrailsCustomPatternTable
  11. connections                  -> Alchemi_ConnectionTable
  12. integration_connections      -> Alchemi_IntegrationConnectionTable
  13. integrations_def             -> Alchemi_IntegrationsDefTable
  14. notifications                -> Alchemi_NotificationTable
  15. notification_templates       -> Alchemi_NotificationTemplateTable
  16. account_notification_templates -> Alchemi_AccountNotificationTemplateTable
  17. discussions                  -> Alchemi_DiscussionTable
  18. user_invites                 -> Alchemi_UserInviteTable
  19. support_tickets              -> Alchemi_SupportTicketTable
  20. access_tokens                -> Alchemi_AccessTokenTable
  21. platform_catalog             -> Alchemi_PlatformCatalogTable
  22. account_override_configs     -> Alchemi_AccountOverrideConfigTable
  23. mvp_configs                  -> Alchemi_MvpConfigTable
  24. mcp_configs                  -> Alchemi_McpConfigTable

Idempotent: uses ON CONFLICT DO NOTHING so it is safe to re-run.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import MigrationRunner, migrate_table, setup_logging, logger, table_exists


# ---------------------------------------------------------------------------
# Table migration configurations
# ---------------------------------------------------------------------------

TABLES = [
    # 1. subscription_plans
    {
        "source_table": "subscription_plans",
        "dest_table": "Alchemi_SubscriptionPlanTable",
        "columns": [
            "id",
            "plan_name",
            "price_monthly",
            "price_yearly",
            "currency",
            "features",
            "limits",
            "is_active",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 2. subscriptions
    {
        "source_table": "subscriptions",
        "dest_table": "Alchemi_SubscriptionTable",
        "columns": [
            "id",
            "account_id",
            "plan_id",
            "system_subscription_id",
            "quantity",
            "start_date",
            "end_date",
            "is_active",
            "razorpay_response",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 3. roles
    {
        "source_table": "roles",
        "dest_table": "Alchemi_RoleTable",
        "columns": [
            "id",
            "account_id",
            "name",
            "type",
            "provider",
            "is_default",
            "is_deleted",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 4. permissions (platform-wide, no account_id)
    {
        "source_table": "permissions",
        "dest_table": "Alchemi_PermissionTable",
        "columns": [
            "id",
            "name",
            "subject",
            "action",
            "is_system_permission",
            "fields",
            "conditions",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 5. role_permissions (unique on role_id, permission_id)
    {
        "source_table": "role_permissions",
        "dest_table": "Alchemi_RolePermissionTable",
        "columns": [
            "id",
            "role_id",
            "permission_id",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["role_id", "permission_id"],
    },
    # 6. account_memberships (unique on account_id, user_id)
    {
        "source_table": "account_memberships",
        "dest_table": "Alchemi_AccountMembershipTable",
        "columns": [
            "id",
            "account_id",
            "user_id",
            "app_role",
            "is_active",
            "joined_at",
            "invited_by",
            "team_id",
            "tenant_preferences",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["account_id", "user_id"],
    },
    # 7. workspaces
    {
        "source_table": "workspaces",
        "dest_table": "Alchemi_WorkspaceTable",
        "columns": [
            "id",
            "account_id",
            "name",
            "description",
            "status",
            "current_analysis_state",
            "is_mvp_ready",
            "product_info",
            "workspace_info",
            "analysis_data",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 8. workspace_members (unique on workspace_id, user_id)
    {
        "source_table": "workspace_members",
        "dest_table": "Alchemi_WorkspaceMemberTable",
        "columns": [
            "id",
            "account_id",
            "workspace_id",
            "user_id",
            "role_id",
            "status",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["workspace_id", "user_id"],
    },
    # 9. guardrails_config (unique on account_id, guard_type)
    {
        "source_table": "guardrails_config",
        "dest_table": "Alchemi_GuardrailsConfigTable",
        "columns": [
            "id",
            "account_id",
            "guard_type",
            "enabled",
            "execution_order",
            "action_on_fail",
            "config",
            "version",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["account_id", "guard_type"],
    },
    # 10. guardrails_custom_patterns
    {
        "source_table": "guardrails_custom_patterns",
        "dest_table": "Alchemi_GuardrailsCustomPatternTable",
        "columns": [
            "id",
            "account_id",
            "guard_type",
            "pattern_name",
            "pattern",
            "description",
            "enabled",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 11. connections
    {
        "source_table": "connections",
        "dest_table": "Alchemi_ConnectionTable",
        "columns": [
            "id",
            "account_id",
            "workspace_id",
            "name",
            "type",
            "status",
            "config",
            "mvp_version_id",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 12. integration_connections (unique on workspace_id, app_name, user_id)
    {
        "source_table": "integration_connections",
        "dest_table": "Alchemi_IntegrationConnectionTable",
        "columns": [
            "id",
            "workspace_id",
            "user_id",
            "connection_level",
            "name",
            "integration_type",
            "app_name",
            "composio_entity_id",
            "composio_connected_account_id",
            "status",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["workspace_id", "app_name", "user_id"],
    },
    # 13. integrations_def (platform-wide, no account_id)
    {
        "source_table": "integrations_def",
        "dest_table": "Alchemi_IntegrationsDefTable",
        "columns": [
            "id",
            "name",
            "description",
            "toolkit",
            "auth_config_id",
            "icon",
            "enabled",
            "display_order",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 14. notifications
    {
        "source_table": "notifications",
        "dest_table": "Alchemi_NotificationTable",
        "columns": [
            "id",
            "account_id",
            "recipient_id",
            "type",
            "title",
            "content",
            "status",
            "read_at",
            "sent_at",
            "metadata",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 15. notification_templates (platform-wide, no account_id)
    {
        "source_table": "notification_templates",
        "dest_table": "Alchemi_NotificationTemplateTable",
        "columns": [
            "id",
            "template_id",
            "title_line",
            "template_content",
            "event_id",
            "type",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 16. account_notification_templates (unique on account_id, template_id)
    {
        "source_table": "account_notification_templates",
        "dest_table": "Alchemi_AccountNotificationTemplateTable",
        "columns": [
            "id",
            "account_id",
            "template_id",
            "overrides",
            "is_active",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["account_id", "template_id"],
    },
    # 17. discussions
    {
        "source_table": "discussions",
        "dest_table": "Alchemi_DiscussionTable",
        "columns": [
            "id",
            "account_id",
            "workspace_id",
            "type",
            "content",
            "parent_object_type",
            "parent_object_id",
            "parent_message_id",
            "resolved",
            "mentions",
            "attachments",
            "reactions",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 18. user_invites
    {
        "source_table": "user_invites",
        "dest_table": "Alchemi_UserInviteTable",
        "columns": [
            "id",
            "account_id",
            "workspace_id",
            "email",
            "role_id",
            "status",
            "token",
            "expires_at",
            "accepted_at",
            "invitation_data",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 19. support_tickets
    {
        "source_table": "support_tickets",
        "dest_table": "Alchemi_SupportTicketTable",
        "columns": [
            "id",
            "account_id",
            "user_profile_id",
            "subject",
            "description",
            "status",
            "priority",
            "assigned_to",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 20. access_tokens
    {
        "source_table": "access_tokens",
        "dest_table": "Alchemi_AccessTokenTable",
        "columns": [
            "id",
            "account_id",
            "name",
            "workspace_ids",
            "token_hash",
            "client_id",
            "scopes",
            "last_used_at",
            "expires_at",
            "revoked",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
    # 21. platform_catalog (PK is "code", not "id")
    {
        "source_table": "platform_catalog",
        "dest_table": "Alchemi_PlatformCatalogTable",
        "columns": [
            "code",
            "name",
            "category",
            "parent_code",
            "value_config",
            "is_active",
            "display_order",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["code"],
    },
    # 22. account_override_configs (unique on account_id, entity_code, scope_type)
    {
        "source_table": "account_override_configs",
        "dest_table": "Alchemi_AccountOverrideConfigTable",
        "columns": [
            "id",
            "account_id",
            "product_code",
            "feature_code",
            "entity_code",
            "name",
            "category",
            "parent_entity_code",
            "action",
            "inherit",
            "value_config",
            "scope_type",
            "scope_id",
            "restriction_json",
            "reason",
            "valid_from",
            "valid_until",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["account_id", "entity_code", "scope_type"],
    },
    # 23. mvp_configs (unique on account_id, name)
    {
        "source_table": "mvp_configs",
        "dest_table": "Alchemi_MvpConfigTable",
        "columns": [
            "id",
            "account_id",
            "workspace_id",
            "name",
            "description",
            "creation_type",
            "mvp_type",
            "framework",
            "commit_count",
            "connections",
            "base_versions",
            "config",
            "access_token",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["account_id", "name"],
    },
    # 24. mcp_configs
    {
        "source_table": "mcp_configs",
        "dest_table": "Alchemi_McpConfigTable",
        "columns": [
            "id",
            "account_id",
            "workspace_id",
            "name",
            "server_name",
            "config",
            "is_active",
            "mvp_version_id",
            "created_at",
            "updated_at",
        ],
        "conflict_columns": ["id"],
    },
]


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------

async def migrate_all_single_source() -> None:
    """Run all single-source table migrations from alchemi-web."""
    async with MigrationRunner("single_source_tables", needs_web=True, needs_ai=False) as runner:
        if not runner.web:
            logger.error("Cannot connect to alchemi-web database -- aborting.")
            return

        total_tables = len(TABLES)
        migrated = 0
        skipped = 0
        failed = 0

        for idx, table_cfg in enumerate(TABLES, start=1):
            source_table = table_cfg["source_table"]
            dest_table = table_cfg["dest_table"]
            logger.info(
                f"--- [{idx}/{total_tables}] {source_table} -> {dest_table} ---"
            )

            # Check if the source table exists before attempting migration
            try:
                source_exists = await table_exists(runner.web, source_table)
            except Exception as exc:
                logger.error(
                    f"  Error checking if {source_table} exists: {exc}"
                )
                failed += 1
                continue

            if not source_exists:
                logger.info(
                    f"  Skipping {source_table} (not found in source)"
                )
                skipped += 1
                continue

            try:
                await migrate_table(
                    source=runner.web,
                    dest=runner.dest,
                    source_table=source_table,
                    dest_table=dest_table,
                    columns=table_cfg["columns"],
                    source_columns=table_cfg.get("source_columns"),
                    conflict_columns=table_cfg.get("conflict_columns"),
                )
                migrated += 1
            except Exception as exc:
                logger.error(f"  Failed to migrate {source_table}: {exc}")
                failed += 1

        logger.info(
            f"=== Summary: {migrated} migrated, {skipped} skipped, "
            f"{failed} failed out of {total_tables} tables ==="
        )


if __name__ == "__main__":
    setup_logging()
    asyncio.run(migrate_all_single_source())
