import json
import os
import uuid
from typing import Any, Dict, List, Optional


def _json(value: Optional[Dict[str, Any]]) -> str:
    return json.dumps(value or {})


def _normalize_email(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip().lower()
    return value or None


def _coerce_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


async def get_account_by_id(prisma_client, account_id: str) -> Optional[Dict[str, Any]]:
    rows = await prisma_client.db.query_raw(
        'SELECT * FROM "Alchemi_AccountTable" WHERE "account_id" = $1 LIMIT 1',
        account_id,
    )
    if not rows:
        return None
    account = dict(rows[0])
    account["metadata"] = _coerce_json(account.get("metadata"))
    return account


async def get_account_by_name(prisma_client, account_name: str) -> Optional[Dict[str, Any]]:
    rows = await prisma_client.db.query_raw(
        'SELECT * FROM "Alchemi_AccountTable" WHERE "account_name" = $1 LIMIT 1',
        account_name,
    )
    if not rows:
        return None
    account = dict(rows[0])
    account["metadata"] = _coerce_json(account.get("metadata"))
    return account


async def get_account_by_zitadel_org_id(
    prisma_client, zitadel_org_id: str
) -> Optional[Dict[str, Any]]:
    rows = await prisma_client.db.query_raw(
        """
        SELECT *
        FROM "Alchemi_AccountTable"
        WHERE "metadata"->>'zitadel_org_id' = $1
        LIMIT 1
        """,
        zitadel_org_id,
    )
    if not rows:
        return None
    account = dict(rows[0])
    account["metadata"] = _coerce_json(account.get("metadata"))
    return account


async def upsert_account(
    prisma_client,
    *,
    account_id: Optional[str],
    account_name: str,
    account_alias: Optional[str],
    domain: Optional[str],
    max_budget: Optional[float],
    metadata: Optional[Dict[str, Any]],
    status: str,
    actor: str,
) -> Dict[str, Any]:
    existing = None
    if account_id:
        existing = await get_account_by_id(prisma_client, account_id)
    if existing is None:
        existing = await get_account_by_name(prisma_client, account_name)

    if existing is None:
        rows = await prisma_client.db.query_raw(
            """
            INSERT INTO "Alchemi_AccountTable" (
              "account_id",
              "account_name",
              "account_alias",
              "domain",
              "status",
              "metadata",
              "max_budget",
              "created_by",
              "updated_at"
            ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            account_id or str(uuid.uuid4()),
            account_name,
            account_alias,
            domain,
            status,
            _json(metadata),
            max_budget,
            actor,
        )
        account = dict(rows[0])
    else:
        new_metadata = existing.get("metadata") if isinstance(existing.get("metadata"), dict) else _coerce_json(existing.get("metadata"))
        if metadata:
            new_metadata.update(metadata)
        rows = await prisma_client.db.query_raw(
            """
            UPDATE "Alchemi_AccountTable"
            SET
              "account_name" = COALESCE($2, "account_name"),
              "account_alias" = $3,
              "domain" = $4,
              "status" = $5,
              "metadata" = $6::jsonb,
              "max_budget" = $7,
              "updated_at" = CURRENT_TIMESTAMP
            WHERE "account_id" = $1
            RETURNING *
            """,
            existing["account_id"],
            account_name,
            account_alias,
            domain,
            status,
            _json(new_metadata),
            max_budget,
        )
        account = dict(rows[0])

    account["metadata"] = _coerce_json(account.get("metadata"))
    return account


async def upsert_control_plane_user(
    prisma_client,
    *,
    user_id: Optional[str],
    user_email: str,
    display_name: Optional[str],
    zitadel_sub: Optional[str],
    primary_account_id: Optional[str],
    metadata: Optional[Dict[str, Any]],
    actor: str,
) -> Dict[str, Any]:
    email = _normalize_email(user_email)
    if email is None:
        raise ValueError("user_email is required")

    lookup_rows = await prisma_client.db.query_raw(
        """
        SELECT *
        FROM "Alchemi_ControlPlaneUserTable"
        WHERE "user_email" = $1
           OR ($2::text IS NOT NULL AND "zitadel_sub" = $2::text)
           OR ($3::text IS NOT NULL AND "user_id" = $3::text)
        ORDER BY "created_at" ASC
        LIMIT 1
        """,
        email,
        zitadel_sub,
        user_id,
    )

    existing = dict(lookup_rows[0]) if lookup_rows else None
    existing_metadata = _coerce_json(existing.get("metadata")) if existing else {}
    if metadata:
        existing_metadata.update(metadata)

    if existing is None:
        rows = await prisma_client.db.query_raw(
            """
            INSERT INTO "Alchemi_ControlPlaneUserTable" (
              "user_id",
              "user_email",
              "display_name",
              "zitadel_sub",
              "status",
              "primary_account_id",
              "metadata",
              "created_by",
              "updated_at"
            ) VALUES ($1, $2, $3, $4, 'active', $5, $6::jsonb, $7, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            user_id or str(uuid.uuid4()),
            email,
            display_name,
            zitadel_sub,
            primary_account_id,
            _json(existing_metadata),
            actor,
        )
        user = dict(rows[0])
    else:
        rows = await prisma_client.db.query_raw(
            """
            UPDATE "Alchemi_ControlPlaneUserTable"
            SET
              "user_email" = $2,
              "display_name" = COALESCE($3, "display_name"),
              "zitadel_sub" = COALESCE($4, "zitadel_sub"),
              "primary_account_id" = COALESCE($5, "primary_account_id"),
              "metadata" = $6::jsonb,
              "updated_by" = $7,
              "updated_at" = CURRENT_TIMESTAMP
            WHERE "user_id" = $1
            RETURNING *
            """,
            existing["user_id"],
            email,
            display_name,
            zitadel_sub,
            primary_account_id,
            _json(existing_metadata),
            actor,
        )
        user = dict(rows[0])

    user["metadata"] = _coerce_json(user.get("metadata"))
    return user


async def ensure_account_membership(
    prisma_client,
    *,
    account_id: str,
    user_id: str,
    membership_role: str,
    membership_status: str,
    is_default: bool,
    metadata: Optional[Dict[str, Any]],
    actor: str,
) -> Dict[str, Any]:
    rows = await prisma_client.db.query_raw(
        """
        INSERT INTO "Alchemi_AccountMembershipTable" (
          "membership_id",
          "account_id",
          "user_id",
          "membership_role",
          "membership_status",
          "is_default",
          "metadata",
          "created_by",
          "updated_at"
        ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, CURRENT_TIMESTAMP)
        ON CONFLICT ("account_id", "user_id")
        DO UPDATE SET
          "membership_role" = EXCLUDED."membership_role",
          "membership_status" = EXCLUDED."membership_status",
          "is_default" = EXCLUDED."is_default",
          "metadata" = EXCLUDED."metadata",
          "updated_by" = EXCLUDED."created_by",
          "updated_at" = CURRENT_TIMESTAMP
        RETURNING *
        """,
        str(uuid.uuid4()),
        account_id,
        user_id,
        membership_role,
        membership_status,
        is_default,
        _json(metadata),
        actor,
    )
    membership = dict(rows[0])
    membership["metadata"] = _coerce_json(membership.get("metadata"))
    return membership


async def delete_account_membership(
    prisma_client,
    *,
    account_id: str,
    user_email: str,
) -> int:
    email = _normalize_email(user_email)
    if email is None:
        return 0
    rows = await prisma_client.db.query_raw(
        """
        DELETE FROM "Alchemi_AccountMembershipTable"
        WHERE "account_id" = $1
          AND "user_id" IN (
            SELECT "user_id"
            FROM "Alchemi_ControlPlaneUserTable"
            WHERE "user_email" = $2
          )
        RETURNING "membership_id"
        """,
        account_id,
        email,
    )
    return len(rows)


async def ensure_role_binding(
    prisma_client,
    *,
    account_id: str,
    principal_type: str,
    principal_id: str,
    role_code: str,
    product_code: Optional[str],
    scope_type: str,
    scope_id: Optional[str],
    metadata: Optional[Dict[str, Any]],
    actor: str,
) -> Dict[str, Any]:
    existing_rows = await prisma_client.db.query_raw(
        """
        SELECT *
        FROM "Alchemi_RoleBindingTable"
        WHERE "account_id" = $1
          AND "principal_type" = $2
          AND "principal_id" = $3
          AND "role_code" = $4
          AND "scope_type" = $5
          AND COALESCE("scope_id", '') = COALESCE($6, '')
          AND COALESCE("product_code", '') = COALESCE($7, '')
        LIMIT 1
        """,
        account_id,
        principal_type,
        principal_id,
        role_code,
        scope_type,
        scope_id,
        product_code,
    )
    if existing_rows:
        role_binding = dict(existing_rows[0])
        role_binding["metadata"] = _coerce_json(role_binding.get("metadata"))
        return role_binding

    rows = await prisma_client.db.query_raw(
        """
        INSERT INTO "Alchemi_RoleBindingTable" (
          "role_binding_id",
          "account_id",
          "principal_type",
          "principal_id",
          "scope_type",
          "scope_id",
          "product_code",
          "role_code",
          "metadata",
          "created_by",
          "updated_at"
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        str(uuid.uuid4()),
        account_id,
        principal_type,
        principal_id,
        scope_type,
        scope_id,
        product_code,
        role_code,
        _json(metadata),
        actor,
    )
    role_binding = dict(rows[0])
    role_binding["metadata"] = _coerce_json(role_binding.get("metadata"))
    return role_binding


async def ensure_product_grant(
    prisma_client,
    *,
    account_id: str,
    user_id: str,
    product_code: str,
    grant_status: str,
    metadata: Optional[Dict[str, Any]],
    actor: str,
) -> Dict[str, Any]:
    rows = await prisma_client.db.query_raw(
        """
        INSERT INTO "Alchemi_ProductGrantTable" (
          "product_grant_id",
          "account_id",
          "user_id",
          "product_code",
          "grant_status",
          "metadata",
          "created_by",
          "updated_at"
        ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, CURRENT_TIMESTAMP)
        ON CONFLICT ("account_id", "user_id", "product_code")
        DO UPDATE SET
          "grant_status" = EXCLUDED."grant_status",
          "metadata" = EXCLUDED."metadata",
          "updated_by" = EXCLUDED."created_by",
          "updated_at" = CURRENT_TIMESTAMP
        RETURNING *
        """,
        str(uuid.uuid4()),
        account_id,
        user_id,
        product_code,
        grant_status,
        _json(metadata),
        actor,
    )
    grant = dict(rows[0])
    grant["metadata"] = _coerce_json(grant.get("metadata"))
    return grant


async def ensure_group(
    prisma_client,
    *,
    account_id: str,
    group_name: str,
    group_kind: str,
    group_slug: Optional[str],
    parent_group_id: Optional[str],
    metadata: Optional[Dict[str, Any]],
    actor: str,
) -> Dict[str, Any]:
    existing_rows = await prisma_client.db.query_raw(
        """
        SELECT *
        FROM "Alchemi_ControlPlaneGroupTable"
        WHERE "account_id" = $1 AND "group_name" = $2
        LIMIT 1
        """,
        account_id,
        group_name,
    )
    if existing_rows:
        group = dict(existing_rows[0])
        group["metadata"] = _coerce_json(group.get("metadata"))
        return group

    rows = await prisma_client.db.query_raw(
        """
        INSERT INTO "Alchemi_ControlPlaneGroupTable" (
          "group_id",
          "account_id",
          "group_name",
          "group_slug",
          "group_kind",
          "parent_group_id",
          "metadata",
          "created_by",
          "updated_at"
        ) VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        str(uuid.uuid4()),
        account_id,
        group_name,
        group_slug,
        group_kind,
        parent_group_id,
        _json(metadata),
        actor,
    )
    group = dict(rows[0])
    group["metadata"] = _coerce_json(group.get("metadata"))
    return group


async def ensure_team(
    prisma_client,
    *,
    account_id: str,
    team_name: str,
    group_id: Optional[str],
    team_slug: Optional[str],
    metadata: Optional[Dict[str, Any]],
    actor: str,
) -> Dict[str, Any]:
    existing_rows = await prisma_client.db.query_raw(
        """
        SELECT *
        FROM "Alchemi_ControlPlaneTeamTable"
        WHERE "account_id" = $1 AND "team_name" = $2
        LIMIT 1
        """,
        account_id,
        team_name,
    )
    if existing_rows:
        team = dict(existing_rows[0])
        team["metadata"] = _coerce_json(team.get("metadata"))
        return team

    rows = await prisma_client.db.query_raw(
        """
        INSERT INTO "Alchemi_ControlPlaneTeamTable" (
          "team_id",
          "account_id",
          "group_id",
          "team_name",
          "team_slug",
          "metadata",
          "created_by",
          "updated_at"
        ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, CURRENT_TIMESTAMP)
        RETURNING *
        """,
        str(uuid.uuid4()),
        account_id,
        group_id,
        team_name,
        team_slug,
        _json(metadata),
        actor,
    )
    team = dict(rows[0])
    team["metadata"] = _coerce_json(team.get("metadata"))
    return team


async def upsert_identity_binding(
    prisma_client,
    *,
    account_id: str,
    provider: str,
    zitadel_org_id: Optional[str],
    issuer_url: Optional[str],
    client_id: Optional[str],
    default_redirect_url: Optional[str],
    sso_enabled: bool,
    config: Optional[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]],
    actor: str,
) -> Dict[str, Any]:
    existing = await prisma_client.db.query_raw(
        'SELECT * FROM "Alchemi_IdentityBindingTable" WHERE "account_id" = $1 LIMIT 1',
        account_id,
    )

    if existing:
        rows = await prisma_client.db.query_raw(
            """
            UPDATE "Alchemi_IdentityBindingTable"
            SET
              "provider" = $2,
              "zitadel_org_id" = $3,
              "issuer_url" = $4,
              "client_id" = $5,
              "default_redirect_url" = $6,
              "sso_enabled" = $7,
              "config" = $8::jsonb,
              "metadata" = $9::jsonb,
              "updated_by" = $10,
              "updated_at" = CURRENT_TIMESTAMP
            WHERE "account_id" = $1
            RETURNING *
            """,
            account_id,
            provider,
            zitadel_org_id,
            issuer_url,
            client_id,
            default_redirect_url,
            sso_enabled,
            _json(config),
            _json(metadata),
            actor,
        )
    else:
        rows = await prisma_client.db.query_raw(
            """
            INSERT INTO "Alchemi_IdentityBindingTable" (
              "identity_binding_id",
              "account_id",
              "provider",
              "zitadel_org_id",
              "issuer_url",
              "client_id",
              "default_redirect_url",
              "sso_enabled",
              "config",
              "metadata",
              "created_by",
              "updated_at"
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11, CURRENT_TIMESTAMP)
            RETURNING *
            """,
            str(uuid.uuid4()),
            account_id,
            provider,
            zitadel_org_id,
            issuer_url,
            client_id,
            default_redirect_url,
            sso_enabled,
            _json(config),
            _json(metadata),
            actor,
        )
    binding = dict(rows[0])
    binding["config"] = _coerce_json(binding.get("config"))
    binding["metadata"] = _coerce_json(binding.get("metadata"))
    return binding


async def _account_admins(prisma_client, account_id: str) -> List[Dict[str, Any]]:
    rows = await prisma_client.db.query_raw(
        """
        SELECT
          u."user_id",
          u."user_email",
          u."display_name",
          m."membership_role",
          rb."role_code"
        FROM "Alchemi_ControlPlaneUserTable" u
        INNER JOIN "Alchemi_AccountMembershipTable" m
          ON m."user_id" = u."user_id"
         AND m."account_id" = $1
         AND m."membership_status" = 'active'
        LEFT JOIN "Alchemi_RoleBindingTable" rb
          ON rb."account_id" = m."account_id"
         AND rb."principal_type" = 'user'
         AND rb."principal_id" = u."user_id"
        WHERE UPPER(COALESCE(m."membership_role", '')) IN ('OWNER', 'ADMIN', 'ACCOUNT_ADMIN')
           OR rb."role_code" IN ('account_owner', 'account_admin', 'platform_admin')
        ORDER BY u."user_email" ASC
        """,
        account_id,
    )
    return [dict(row) for row in rows]


async def get_account_identity_binding(prisma_client, account_id: str) -> Optional[Dict[str, Any]]:
    rows = await prisma_client.db.query_raw(
        'SELECT * FROM "Alchemi_IdentityBindingTable" WHERE "account_id" = $1 LIMIT 1',
        account_id,
    )
    if not rows:
        return None
    binding = dict(rows[0])
    binding["config"] = _coerce_json(binding.get("config"))
    binding["metadata"] = _coerce_json(binding.get("metadata"))
    return binding


async def list_accounts(prisma_client) -> List[Dict[str, Any]]:
    rows = await prisma_client.db.query_raw(
        'SELECT * FROM "Alchemi_AccountTable" ORDER BY "created_at" DESC'
    )
    accounts: List[Dict[str, Any]] = []
    for row in rows:
        account = dict(row)
        account["metadata"] = _coerce_json(account.get("metadata"))
        if account["metadata"].get("system_account"):
            continue
        account["admins"] = await _account_admins(prisma_client, account["account_id"])
        account["identity_binding"] = await get_account_identity_binding(
            prisma_client, account["account_id"]
        )
        accounts.append(account)
    return accounts


async def list_account_members(prisma_client, account_id: str) -> List[Dict[str, Any]]:
    rows = await prisma_client.db.query_raw(
        """
        SELECT
          u."user_id",
          u."user_email",
          u."display_name",
          u."zitadel_sub",
          u."status" AS "user_status",
          m."membership_id",
          m."membership_role",
          m."membership_status",
          m."is_default",
          m."metadata" AS "membership_metadata"
        FROM "Alchemi_AccountMembershipTable" m
        INNER JOIN "Alchemi_ControlPlaneUserTable" u ON u."user_id" = m."user_id"
        WHERE m."account_id" = $1
        ORDER BY u."user_email" ASC
        """,
        account_id,
    )
    members = [dict(row) for row in rows]
    for member in members:
        member["membership_metadata"] = _coerce_json(member.get("membership_metadata"))
    return members


async def get_user_context(
    prisma_client,
    *,
    user_email: Optional[str] = None,
    user_id: Optional[str] = None,
    zitadel_sub: Optional[str] = None,
    active_account_id: Optional[str] = None,
) -> Dict[str, Any]:
    rows = await prisma_client.db.query_raw(
        """
        SELECT *
        FROM "Alchemi_ControlPlaneUserTable"
        WHERE ($1::text IS NOT NULL AND "user_email" = $1::text)
           OR ($2::text IS NOT NULL AND "user_id" = $2::text)
           OR ($3::text IS NOT NULL AND "zitadel_sub" = $3::text)
        ORDER BY "created_at" ASC
        LIMIT 1
        """,
        _normalize_email(user_email),
        user_id,
        zitadel_sub,
    )

    if not rows:
        return {
            "user": None,
            "memberships": [],
            "platform_roles": [],
            "product_grants": [],
            "active_account_id": active_account_id,
        }

    user = dict(rows[0])
    user["metadata"] = _coerce_json(user.get("metadata"))
    memberships = await prisma_client.db.query_raw(
        """
        SELECT
          m.*,
          a."account_name",
          a."account_alias",
          a."domain",
          a."status" AS "account_status"
        FROM "Alchemi_AccountMembershipTable" m
        INNER JOIN "Alchemi_AccountTable" a ON a."account_id" = m."account_id"
        WHERE m."user_id" = $1
          AND m."membership_status" = 'active'
        ORDER BY m."is_default" DESC, m."created_at" ASC
        """,
        user["user_id"],
    )
    membership_rows = [dict(row) for row in memberships]
    for membership in membership_rows:
        membership["metadata"] = _coerce_json(membership.get("metadata"))

    role_rows = await prisma_client.db.query_raw(
        """
        SELECT *
        FROM "Alchemi_RoleBindingTable"
        WHERE "principal_type" = 'user'
          AND "principal_id" = $1
        """,
        user["user_id"],
    )
    platform_roles = sorted(
        {
            row["role_code"]
            for row in role_rows
            if row.get("product_code") in (None, "", "platform-admin")
        }
    )

    grant_rows = await prisma_client.db.query_raw(
        """
        SELECT *
        FROM "Alchemi_ProductGrantTable"
        WHERE "user_id" = $1
          AND "grant_status" = 'active'
        """,
        user["user_id"],
    )
    product_grants = sorted({row["product_code"] for row in grant_rows})

    resolved_active_account_id = active_account_id
    if resolved_active_account_id is None and membership_rows:
        default_membership = next(
            (row for row in membership_rows if row.get("is_default")),
            membership_rows[0],
        )
        resolved_active_account_id = default_membership["account_id"]

    return {
        "user": user,
        "memberships": membership_rows,
        "platform_roles": platform_roles,
        "product_grants": product_grants,
        "active_account_id": resolved_active_account_id,
    }


def get_litellm_user_role_from_context(context: Optional[Dict[str, Any]]) -> str:
    if not context:
        return "internal_user_viewer"

    platform_roles = set(context.get("platform_roles") or [])
    if "platform_super_admin" in platform_roles or "platform_admin" in platform_roles:
        return "proxy_admin"

    memberships = context.get("memberships") or []
    if not memberships:
        return "internal_user_viewer"

    active_account_id = context.get("active_account_id")
    active_membership = next(
        (
            membership
            for membership in memberships
            if membership.get("account_id") == active_account_id
        ),
        memberships[0],
    )
    membership_role = str(active_membership.get("membership_role") or "").upper()

    if membership_role in {"OWNER", "ADMIN", "ACCOUNT_ADMIN"}:
        return "proxy_admin"
    if membership_role == "VIEWER":
        return "internal_user_viewer"
    if membership_role in {"MEMBER", "USER"}:
        return "internal_user"
    return "internal_user_viewer"


async def resolve_account_for_user(
    prisma_client,
    *,
    user_email: Optional[str] = None,
    zitadel_sub: Optional[str] = None,
) -> Optional[str]:
    context = await get_user_context(
        prisma_client,
        user_email=user_email,
        zitadel_sub=zitadel_sub,
    )
    return context.get("active_account_id")


async def resolve_sso_for_email(prisma_client, email: str) -> Dict[str, Any]:
    email = _normalize_email(email)
    if email is None or "@" not in email:
        return {"method": "password", "account_id": None, "sso_enabled": False}

    domain = email.split("@", 1)[1]

    rows = await prisma_client.db.query_raw(
        """
        SELECT a."account_id"
        FROM "Alchemi_AccountTable" a
        INNER JOIN "Alchemi_IdentityBindingTable" ib
          ON ib."account_id" = a."account_id"
        WHERE a."status" = 'active'
          AND ib."sso_enabled" = TRUE
          AND (
            a."domain" = $1
            OR ib."config"->'domains'->>'primary_domain' = $1
            OR EXISTS (
              SELECT 1
              FROM jsonb_array_elements_text(
                COALESCE(ib."config"->'domains'->'additional_domains', '[]'::jsonb)
              ) AS configured_domain(value)
              WHERE configured_domain.value = $1
            )
            OR a."account_id" IN (
              SELECT m."account_id"
              FROM "Alchemi_ControlPlaneUserTable" u
              INNER JOIN "Alchemi_AccountMembershipTable" m
                ON m."user_id" = u."user_id"
              WHERE u."user_email" = $2
                AND m."membership_status" = 'active'
            )
          )
        ORDER BY a."created_at" ASC
        LIMIT 1
        """,
        domain,
        email,
    )

    account_id = rows[0]["account_id"] if rows else None
    if account_id:
        return {
            "method": "sso",
            "account_id": account_id,
            "sso_enabled": True,
            "sso_url": f"/sso/key/generate?account_id={account_id}",
        }

    if _zitadel_generic_sso_enabled():
        return {
            "method": "sso",
            "account_id": None,
            "sso_enabled": True,
            "sso_url": "/sso/key/generate",
        }

    return {"method": "password", "account_id": None, "sso_enabled": False}


def _zitadel_generic_sso_enabled() -> bool:
    return bool(
        os.getenv("GENERIC_CLIENT_ID")
        and os.getenv("GENERIC_AUTHORIZATION_ENDPOINT")
        and os.getenv("GENERIC_TOKEN_ENDPOINT")
    )


async def get_copilot_projection(prisma_client, account_id: str) -> Dict[str, Any]:
    account = await get_account_by_id(prisma_client, account_id)
    if account is None:
        raise ValueError("Account not found")

    member_rows = await list_account_members(prisma_client, account_id)
    user_ids = [row["user_id"] for row in member_rows]

    groups = await prisma_client.db.query_raw(
        'SELECT * FROM "Alchemi_ControlPlaneGroupTable" WHERE "account_id" = $1 ORDER BY "group_name" ASC',
        account_id,
    )
    teams = await prisma_client.db.query_raw(
        'SELECT * FROM "Alchemi_ControlPlaneTeamTable" WHERE "account_id" = $1 ORDER BY "team_name" ASC',
        account_id,
    )
    grants = await prisma_client.db.query_raw(
        'SELECT * FROM "Alchemi_ProductGrantTable" WHERE "account_id" = $1 ORDER BY "product_code" ASC',
        account_id,
    )

    users = []
    if user_ids:
        users = await prisma_client.db.query_raw(
            """
            SELECT *
            FROM "Alchemi_ControlPlaneUserTable"
            WHERE "user_id" = ANY($1::text[])
            ORDER BY "user_email" ASC
            """,
            user_ids,
        )

    return {
        "accounts": [account],
        "users": [dict(row) for row in users],
        "account_memberships": member_rows,
        "groups": [dict(row) for row in groups],
        "teams": [dict(row) for row in teams],
        "product_grants": [dict(row) for row in grants],
        "account_quota_summary": account.get("metadata", {}).get("quota_summary", {}),
    }
