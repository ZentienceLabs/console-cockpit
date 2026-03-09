#!/usr/bin/env python3
"""
Phase 1 migration tool:

- hard-clears the new target databases
- rebuilds Console schema via Prisma migrations
- clones shared/control-plane tables into devconsolev2_db
- clones Copilot projection + operational tables into devappv2_db
- optionally clones the AI database
- backfills Console control-plane tables from the old Copilot dataset
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row


ROOT = Path("/workspaces/console-cockpit")
PLATFORM_ACCOUNT_ID = "platform-admin"

CONTROL_PLANE_SOURCE_TABLES = [
    "accounts",
    "users",
    "account_memberships",
    "groups",
    "teams",
    "admin_users",
    "subscriptions",
    "subscriptionplans",
    "account_quotas",
    "account_entitlements",
    "billable_metrics",
    "plan_charges",
    "feature_catalog",
    "platform_catalog",
]

APP_PROJECTION_TABLES = [
    "accounts",
    "users",
    "account_memberships",
    "groups",
    "teams",
    "subscriptions",
    "subscriptionplans",
    "account_quotas",
    "account_entitlements",
    "feature_catalog",
    "platform_catalog",
]

APP_OPERATIONAL_TABLES = [
    "workspaces",
    "workspace_members",
    "roles",
    "permissions",
    "role_permissions",
    "userinvites",
    "agents_def",
    "agent_groups",
    "agent_group_members",
    "agent_marketplace",
    "mvp_connections",
    "account_connections",
    "mvp_mcpconfigs",
    "mvp_versions",
    "guardrails_config",
    "guardrails_custom_patterns",
    "guardrails_audit_log",
    "discussions",
    "notifications",
    "supporttickets",
    "cost_tracking",
    "accesstokens",
]


def log(message: str) -> None:
    print(f"[phase1] {message}")


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def run(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> None:
    log("running: " + " ".join(cmd))
    subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=check,
    )


def reset_database(database_url: str, label: str) -> None:
    log(f"resetting {label}")
    run(
        [
            "psql",
            database_url,
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            'DROP SCHEMA public CASCADE; CREATE SCHEMA public;',
        ]
    )


def list_source_tables(database_url: str) -> set[str]:
    with psycopg.connect(database_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                """
            )
            return {row["tablename"] for row in cur.fetchall()}


def clone_tables(source_url: str, target_url: str, tables: Iterable[str], label: str) -> None:
    existing = list_source_tables(source_url)
    selected = [table for table in tables if table in existing]
    if not selected:
        log(f"no tables to clone for {label}")
        return

    log(f"cloning {len(selected)} tables into {label}")
    schema_args: list[str] = [
        "pg_dump",
        "--schema-only",
        "--no-owner",
        "--no-privileges",
        source_url,
    ]
    data_args: list[str] = ["pg_dump", "--data-only", "--inserts", "--no-owner", "--no-privileges"]
    for table in selected:
        data_args.extend(["-t", table])
    data_args.append(source_url)

    with tempfile.NamedTemporaryFile(suffix=".sql") as schema_file:
        with open(schema_file.name, "wb") as handle:
            subprocess.run(schema_args, check=True, stdout=handle)
        run(
            ["psql", target_url, "-v", "ON_ERROR_STOP=0", "-f", schema_file.name],
            check=False,
        )

    with tempfile.NamedTemporaryFile(suffix=".sql") as data_file:
        with open(data_file.name, "wb") as handle:
            subprocess.run(data_args, check=True, stdout=handle)
        run(["psql", target_url, "-v", "ON_ERROR_STOP=1", "-f", data_file.name])


def sync_console_schema(console_database_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = console_database_url
    run(["bash", "./scripts/deploy.sh", "migrate"], cwd=ROOT, env=env)


def _json(value) -> str:
    return json.dumps(value or {}, default=str)


def _normalize_status(value: str | None) -> str:
    if not value:
        return "active"
    return value.lower()


def _normalize_account_name(name: str | None, domain: str | None, account_id: str) -> str:
    account_id_str = str(account_id)
    if name and name.strip():
        return name.strip()
    if domain and domain.strip():
        return domain.strip()
    return f"Account {account_id_str[:8]}"


def _unique_account_name(base_name: str, account_id: str, used_names: set[str]) -> str:
    account_id_str = str(account_id)
    if base_name not in used_names:
        used_names.add(base_name)
        return base_name

    candidate = f"{base_name} ({account_id_str[:8]})"
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate

    suffix = 2
    while True:
        candidate = f"{base_name} ({account_id_str[:8]}-{suffix})"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        suffix += 1


def populate_control_plane(source_url: str, console_url: str) -> None:
    issuer_url = optional_env("ALCHEMI_ZITADEL_ISSUER") or optional_env("NEXT_PUBLIC_ZITADEL_ISSUER")
    client_id = optional_env("ALCHEMI_ZITADEL_CLIENT_ID") or optional_env("NEXT_PUBLIC_ZITADEL_CLIENT_ID")
    default_redirect = optional_env("ALCHEMI_CONSOLE_REDIRECT_URL") or optional_env("NEXT_PUBLIC_CONSOLE_URL")

    with psycopg.connect(source_url, row_factory=dict_row) as source_conn, psycopg.connect(
        console_url
    ) as target_conn:
        with source_conn.cursor() as source, target_conn.cursor() as target:
            log("backfilling control-plane accounts")
            source.execute(
                """
                SELECT id, name, type, status, domain, billing_info, billing_email,
                       subscription_plan, auth_org_id, settings, created_by, updated_by
                FROM accounts
                ORDER BY id
                """
            )
            account_rows = source.fetchall()
            base_name_counts = Counter(
                _normalize_account_name(row["name"], row["domain"], row["id"]) for row in account_rows
            )
            used_account_names: set[str] = set()

            for row in account_rows:
                base_name = _normalize_account_name(row["name"], row["domain"], row["id"])
                account_name = _unique_account_name(base_name, row["id"], used_account_names)
                metadata = {
                    "type": row["type"],
                    "settings": row["settings"],
                    "billing_info": row["billing_info"],
                    "billing_email": row["billing_email"],
                    "subscription_plan": row["subscription_plan"],
                    "auth_org_id": row["auth_org_id"],
                    "legacy_account_name": row["name"],
                    "legacy_account_name_collision": base_name_counts[base_name] > 1,
                    "source": "legacy_devapp_db",
                }
                target.execute(
                    """
                    INSERT INTO "Alchemi_AccountTable" (
                      "account_id", "account_name", "account_alias", "domain", "status",
                      "metadata", "created_by", "updated_at"
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT ("account_id")
                    DO UPDATE SET
                      "account_name" = EXCLUDED."account_name",
                      "account_alias" = EXCLUDED."account_alias",
                      "domain" = EXCLUDED."domain",
                      "status" = EXCLUDED."status",
                      "metadata" = EXCLUDED."metadata",
                      "updated_at" = CURRENT_TIMESTAMP
                    """,
                    (
                        row["id"],
                        account_name,
                        row["domain"],
                        row["domain"],
                        _normalize_status(row["status"]),
                        _json(metadata),
                        row["created_by"],
                    ),
                )
                if row["auth_org_id"]:
                    target.execute(
                        """
                        INSERT INTO "Alchemi_IdentityBindingTable" (
                          "identity_binding_id", "account_id", "provider", "zitadel_org_id",
                          "issuer_url", "client_id", "default_redirect_url", "sso_enabled",
                          "config", "metadata", "created_by", "updated_at"
                        )
                        VALUES (
                          %s, %s, 'zitadel', %s, %s, %s, %s, TRUE,
                          '{}'::jsonb, '{"source":"legacy_devapp_db"}'::jsonb, 'migration', CURRENT_TIMESTAMP
                        )
                        ON CONFLICT ("account_id")
                        DO UPDATE SET
                          "zitadel_org_id" = EXCLUDED."zitadel_org_id",
                          "issuer_url" = COALESCE(EXCLUDED."issuer_url", "Alchemi_IdentityBindingTable"."issuer_url"),
                          "client_id" = COALESCE(EXCLUDED."client_id", "Alchemi_IdentityBindingTable"."client_id"),
                          "default_redirect_url" = COALESCE(EXCLUDED."default_redirect_url", "Alchemi_IdentityBindingTable"."default_redirect_url"),
                          "sso_enabled" = TRUE,
                          "updated_at" = CURRENT_TIMESTAMP
                        """,
                        (
                            str(uuid4()),
                            row["id"],
                            row["auth_org_id"],
                            issuer_url,
                            client_id,
                            default_redirect,
                        ),
                    )

            log("backfilling control-plane users")
            source.execute(
                """
                SELECT id, email, name, ad_user_id, is_active, global_preferences
                FROM users
                """
            )
            for row in source.fetchall():
                target.execute(
                    """
                    INSERT INTO "Alchemi_ControlPlaneUserTable" (
                      "user_id", "user_email", "display_name", "zitadel_sub", "status",
                      "primary_account_id", "metadata", "created_by", "updated_at"
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, 'migration', CURRENT_TIMESTAMP)
                    ON CONFLICT ("user_id")
                    DO UPDATE SET
                      "user_email" = EXCLUDED."user_email",
                      "display_name" = EXCLUDED."display_name",
                      "zitadel_sub" = EXCLUDED."zitadel_sub",
                      "status" = EXCLUDED."status",
                      "primary_account_id" = EXCLUDED."primary_account_id",
                      "metadata" = EXCLUDED."metadata",
                      "updated_at" = CURRENT_TIMESTAMP
                    """,
                    (
                        row["id"],
                        row["email"].lower(),
                        row["name"],
                        row["ad_user_id"],
                        "active" if row["is_active"] else "inactive",
                        (row["global_preferences"] or {}).get("activeAccount") if isinstance(row["global_preferences"], dict) else None,
                        _json(row["global_preferences"]),
                    ),
                )

            log("backfilling control-plane memberships and grants")
            source.execute(
                """
                SELECT account_id, user_id, app_role, is_active, tenant_preferences, team_id, invited_by
                FROM account_memberships
                """
            )
            for row in source.fetchall():
                metadata = {
                    "tenant_preferences": row["tenant_preferences"],
                    "team_id": row["team_id"],
                    "invited_by": row["invited_by"],
                    "source": "legacy_devapp_db",
                }
                target.execute(
                    """
                    INSERT INTO "Alchemi_AccountMembershipTable" (
                      "membership_id", "account_id", "user_id", "membership_role",
                      "membership_status", "is_default", "metadata", "created_by", "updated_at"
                    )
                    VALUES (
                      %s, %s, %s, %s, %s, FALSE, %s::jsonb, 'migration', CURRENT_TIMESTAMP
                    )
                    ON CONFLICT ("account_id", "user_id")
                    DO UPDATE SET
                      "membership_role" = EXCLUDED."membership_role",
                      "membership_status" = EXCLUDED."membership_status",
                      "metadata" = EXCLUDED."metadata",
                      "updated_at" = CURRENT_TIMESTAMP
                    """,
                    (
                        str(uuid4()),
                        row["account_id"],
                        row["user_id"],
                        row["app_role"],
                        "active" if row["is_active"] else "inactive",
                        _json(metadata),
                    ),
                )
                for product_code in ("console", "copilot"):
                    target.execute(
                        """
                        INSERT INTO "Alchemi_ProductGrantTable" (
                          "product_grant_id", "account_id", "user_id", "product_code",
                          "grant_status", "metadata", "created_by", "updated_at"
                        )
                        VALUES (
                          %s, %s, %s, %s, %s,
                          '{"source":"legacy_devapp_db"}'::jsonb, 'migration', CURRENT_TIMESTAMP
                        )
                        ON CONFLICT ("account_id", "user_id", "product_code")
                        DO UPDATE SET
                          "grant_status" = EXCLUDED."grant_status",
                          "updated_at" = CURRENT_TIMESTAMP
                        """,
                        (
                            str(uuid4()),
                            row["account_id"],
                            row["user_id"],
                            product_code,
                            "active" if row["is_active"] else "inactive",
                        ),
                    )
                if row["app_role"] in ("admin", "owner"):
                    target.execute(
                        """
                        INSERT INTO "Alchemi_RoleBindingTable" (
                          "role_binding_id", "account_id", "principal_type", "principal_id",
                          "scope_type", "scope_id", "product_code", "role_code", "metadata",
                          "created_by", "updated_at"
                        )
                        VALUES (
                          %s, %s, 'user', %s, 'account', %s, NULL, 'account_admin',
                          '{"source":"legacy_devapp_db"}'::jsonb, 'migration', CURRENT_TIMESTAMP
                        )
                        ON CONFLICT DO NOTHING
                        """,
                        (str(uuid4()), row["account_id"], row["user_id"], row["account_id"]),
                    )

            log("backfilling control-plane groups")
            source.execute(
                """
                SELECT id, account_id, name, description, is_default, owner_id, contact_email, created_by, updated_by
                FROM groups
                """
            )
            for row in source.fetchall():
                target.execute(
                    """
                    INSERT INTO "Alchemi_ControlPlaneGroupTable" (
                      "group_id", "account_id", "group_name", "group_slug", "group_kind",
                      "metadata", "created_by", "updated_by", "updated_at"
                    )
                    VALUES (
                      %s, %s, %s, %s, 'org', %s::jsonb, %s, %s, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT ("group_id")
                    DO UPDATE SET
                      "group_name" = EXCLUDED."group_name",
                      "group_slug" = EXCLUDED."group_slug",
                      "metadata" = EXCLUDED."metadata",
                      "updated_at" = CURRENT_TIMESTAMP
                    """,
                    (
                        row["id"],
                        row["account_id"],
                        row["name"],
                        row["name"].lower().replace(" ", "-"),
                        _json(
                            {
                                "description": row["description"],
                                "is_default": row["is_default"],
                                "owner_id": row["owner_id"],
                                "contact_email": row["contact_email"],
                            }
                        ),
                        row["created_by"],
                        row["updated_by"],
                    ),
                )

            log("backfilling control-plane teams")
            source.execute(
                """
                SELECT t.id, t.group_id, t.name, t.description, t.is_default, t.owner_id,
                       t.contact_email, t.created_by, t.updated_by, g.account_id
                FROM teams t
                INNER JOIN groups g ON g.id = t.group_id
                """
            )
            for row in source.fetchall():
                target.execute(
                    """
                    INSERT INTO "Alchemi_ControlPlaneTeamTable" (
                      "team_id", "account_id", "group_id", "team_name", "team_slug",
                      "metadata", "created_by", "updated_by", "updated_at"
                    )
                    VALUES (
                      %s, %s, %s, %s, %s, %s::jsonb, %s, %s, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT ("team_id")
                    DO UPDATE SET
                      "team_name" = EXCLUDED."team_name",
                      "team_slug" = EXCLUDED."team_slug",
                      "metadata" = EXCLUDED."metadata",
                      "updated_at" = CURRENT_TIMESTAMP
                    """,
                    (
                        row["id"],
                        row["account_id"],
                        row["group_id"],
                        row["name"],
                        row["name"].lower().replace(" ", "-"),
                        _json(
                            {
                                "description": row["description"],
                                "is_default": row["is_default"],
                                "owner_id": row["owner_id"],
                                "contact_email": row["contact_email"],
                            }
                        ),
                        row["created_by"],
                        row["updated_by"],
                    ),
                )

            log("creating synthetic platform-admin account")
            target.execute(
                """
                INSERT INTO "Alchemi_AccountTable" (
                  "account_id", "account_name", "account_alias", "status",
                  "metadata", "created_by", "updated_at"
                )
                VALUES (
                  %s, 'Platform Admin', 'platform-admin', 'active',
                  '{"system_account":true}'::jsonb, 'migration', CURRENT_TIMESTAMP
                )
                ON CONFLICT ("account_id")
                DO NOTHING
                """,
                (PLATFORM_ACCOUNT_ID,),
            )

            log("backfilling platform-admin role bindings")
            source.execute(
                """
                SELECT id, email, name, ad_user_id, app_role, is_active, global_preferences
                FROM admin_users
                WHERE is_active = TRUE
                """
            )
            for row in source.fetchall():
                target.execute(
                    """
                    INSERT INTO "Alchemi_ControlPlaneUserTable" (
                      "user_id", "user_email", "display_name", "zitadel_sub", "status",
                      "metadata", "created_by", "updated_at"
                    )
                    VALUES (%s, %s, %s, %s, 'active', %s::jsonb, 'migration', CURRENT_TIMESTAMP)
                    ON CONFLICT ("user_id")
                    DO UPDATE SET
                      "user_email" = EXCLUDED."user_email",
                      "display_name" = EXCLUDED."display_name",
                      "zitadel_sub" = EXCLUDED."zitadel_sub",
                      "status" = 'active',
                      "metadata" = EXCLUDED."metadata",
                      "updated_at" = CURRENT_TIMESTAMP
                    """,
                    (
                        row["id"],
                        row["email"].lower(),
                        row["name"],
                        row["ad_user_id"],
                        _json(row["global_preferences"]),
                    ),
                )
                target.execute(
                    """
                    INSERT INTO "Alchemi_ProductGrantTable" (
                      "product_grant_id", "account_id", "user_id", "product_code",
                      "grant_status", "metadata", "created_by", "updated_at"
                    )
                    VALUES (
                      %s, %s, %s, 'platform-admin', 'active',
                      '{"source":"legacy_admin_users"}'::jsonb, 'migration', CURRENT_TIMESTAMP
                    )
                    ON CONFLICT ("account_id", "user_id", "product_code")
                    DO UPDATE SET
                      "grant_status" = 'active',
                      "updated_at" = CURRENT_TIMESTAMP
                    """,
                    (str(uuid4()), PLATFORM_ACCOUNT_ID, row["id"]),
                )
                target.execute(
                    """
                    INSERT INTO "Alchemi_RoleBindingTable" (
                      "role_binding_id", "account_id", "principal_type", "principal_id",
                      "scope_type", "scope_id", "product_code", "role_code", "metadata",
                      "created_by", "updated_at"
                    )
                    VALUES (
                      %s, %s, 'user', %s, 'platform', NULL, 'platform-admin',
                      'platform_admin', %s::jsonb, 'migration', CURRENT_TIMESTAMP
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        str(uuid4()),
                        PLATFORM_ACCOUNT_ID,
                        row["id"],
                        _json({"source": "legacy_admin_users", "legacy_role": row["app_role"]}),
                    ),
                )

        target_conn.commit()


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    mode = args[0] if args else "full"
    source_app_url = require_env("SOURCE_APP_DATABASE_URL")
    target_console_url = require_env("TARGET_CONSOLE_DATABASE_URL")
    if mode == "populate-control-plane":
        populate_control_plane(source_app_url, target_console_url)
        log("populate-control-plane complete")
        return 0
    if mode != "full":
        raise RuntimeError(f"Unsupported mode: {mode}")

    target_app_url = require_env("TARGET_APP_DATABASE_URL")
    target_ai_url = require_env("TARGET_AI_DATABASE_URL")
    source_ai_url = optional_env("SOURCE_AI_DATABASE_URL")

    reset_database(target_console_url, "target console db")
    reset_database(target_app_url, "target app db")
    reset_database(target_ai_url, "target ai db")

    sync_console_schema(target_console_url)

    clone_tables(source_app_url, target_console_url, CONTROL_PLANE_SOURCE_TABLES, "console canonical mirror")
    clone_tables(
        source_app_url,
        target_app_url,
        APP_PROJECTION_TABLES + APP_OPERATIONAL_TABLES,
        "app projection + operational tables",
    )
    if source_ai_url:
        clone_tables(source_ai_url, target_ai_url, list_source_tables(source_ai_url), "ai database")

    populate_control_plane(source_app_url, target_console_url)
    log("phase 1 reset + migration complete")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"failed: {exc}")
        raise
