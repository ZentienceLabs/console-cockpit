"""
Migrate copilot data from alchemi-web Sequelize tables to copilot.* schema.

Reads from alchemi-web's PostgreSQL tables (public schema) and inserts into
the console-cockpit copilot.* tables. All INSERTs use ON CONFLICT DO NOTHING
for idempotent re-runs.

Environment variables:
  ALCHEMI_WEB_DATABASE_URL  - Connection string for alchemi-web DB (source)
  DATABASE_URL              - Connection string for console-cockpit DB (target)

Usage:
  python -m alchemi.scripts.migrate_copilot_data
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from decimal import Decimal
from typing import Any, Dict, List

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SRC_URL = os.getenv("ALCHEMI_WEB_DATABASE_URL", "")
DST_URL = os.getenv("DATABASE_URL", "")


async def migrate_table(
    src: asyncpg.Connection,
    dst: asyncpg.Connection,
    source_table: str,
    target_table: str,
    select_sql: str,
    insert_sql: str,
    transform=None,
) -> int:
    """Migrate rows from source table to target table.

    Args:
        src: Source database connection
        dst: Target database connection
        source_table: Name of the source table (for logging)
        target_table: Name of the target table (for logging)
        select_sql: SELECT query for the source
        insert_sql: INSERT ... ON CONFLICT DO NOTHING for the target
        transform: Optional function to transform each row dict before insert

    Returns:
        Number of rows inserted
    """
    rows = await src.fetch(select_sql)
    if not rows:
        logger.info(f"  {source_table} -> {target_table}: 0 rows (empty source)")
        return 0

    inserted = 0
    for row in rows:
        data = dict(row)
        if transform:
            data = transform(data)
        try:
            result = await dst.execute(insert_sql, *data.values())
            if "INSERT" in result:
                inserted += 1
        except Exception as e:
            logger.warning(f"  Skipping row in {target_table}: {e}")

    logger.info(
        f"  {source_table} -> {target_table}: "
        f"{inserted}/{len(rows)} rows inserted"
    )
    return inserted


def _json_str(val: Any) -> str:
    """Convert a value to JSON string if it's a dict/list, otherwise return as-is."""
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    if val is None:
        return "{}"
    return str(val)


_USER_SCOPE_NAMESPACE = uuid.UUID("d4f71676-e638-4cb8-af84-e810ca1da308")
_MODEL_CATALOG_NAMESPACE = uuid.UUID("9b917801-ad4d-45fd-b233-ebd444f7dd64")


def _normalize_value(val: Any) -> Any:
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, list):
        return [_normalize_value(v) for v in val]
    if isinstance(val, dict):
        return {k: _normalize_value(v) for k, v in val.items()}
    return val


def _normalize_row(row: Any) -> Dict[str, Any]:
    data = dict(row)
    return {k: _normalize_value(v) for k, v in data.items()}


def _scoped_user_id(account_id: str, user_id: str) -> str:
    """Create deterministic account-scoped user IDs for copilot.users."""
    return str(uuid.uuid5(_USER_SCOPE_NAMESPACE, f"{account_id}:{user_id}"))


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y", "active", "enabled"}
    return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


async def _table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    return bool(
        await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table_name}")
    )


async def _column_exists(
    conn: asyncpg.Connection, table_name: str, column_name: str
) -> bool:
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = $1
                AND column_name = $2
            )
            """,
            table_name,
            column_name,
        )
    )


async def _first_existing_table(
    conn: asyncpg.Connection, candidates: List[str]
) -> str:
    for table in candidates:
        if await _table_exists(conn, table):
            return table
    return ""


async def run_migration():
    if not SRC_URL:
        logger.error("ALCHEMI_WEB_DATABASE_URL is not set")
        sys.exit(1)
    if not DST_URL:
        logger.error("DATABASE_URL is not set")
        sys.exit(1)

    logger.info("Connecting to source (alchemi-web) database...")
    src = await asyncpg.connect(SRC_URL, statement_cache_size=0)

    logger.info("Connecting to target (console-cockpit) database...")
    dst = await asyncpg.connect(DST_URL, statement_cache_size=0)

    summary: Dict[str, int] = {}

    try:
        # -------------------------------------------------------------------
        # 1. credit_budget
        # -------------------------------------------------------------------
        if await _table_exists(src, "credit_budget"):
            logger.info("Migrating credit_budget...")
            rows = await src.fetch(
                "SELECT id, account_id, budget_plan_id, scope_type, scope_id, "
                "allocated, limit_amount, overflow_cap, used, overflow_used, "
                "cycle_start, cycle_end, created_at, updated_at "
                "FROM credit_budget"
            )
            count = 0
            for row in rows:
                r = _normalize_row(row)
                if not r.get("account_id"):
                    logger.warning("  Skipping credit_budget row with null account_id")
                    continue
                try:
                    scope_type_raw = str(r.get("scope_type") or "").strip().lower()
                    scope_type_map = {
                        "organization": "group",
                    }
                    scope_type = scope_type_map.get(scope_type_raw, scope_type_raw)
                    if scope_type not in {"account", "group", "team", "user"}:
                        logger.warning(
                            f"  Skipping credit_budget row with invalid scope_type={r.get('scope_type')}"
                        )
                        continue
                    result = await dst.execute(
                        "INSERT INTO copilot.credit_budget "
                        "(id, account_id, budget_plan_id, scope_type, scope_id, "
                        "allocated, limit_amount, overflow_cap, used, overflow_used, "
                        "cycle_start, cycle_end, created_at, updated_at) "
                        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) "
                        "ON CONFLICT DO NOTHING",
                        r["id"], r["account_id"], r["budget_plan_id"],
                        scope_type, r["scope_id"],
                        r["allocated"], r["limit_amount"], r["overflow_cap"],
                        r["used"], r["overflow_used"],
                        r["cycle_start"], r["cycle_end"],
                        r["created_at"], r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping credit_budget row: {e}")
            summary["credit_budget"] = count
            logger.info(f"  credit_budget: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping credit_budget migration (source table missing)")
            summary["credit_budget"] = 0

        # -------------------------------------------------------------------
        # 2. budget_plans
        # -------------------------------------------------------------------
        if await _table_exists(src, "budget_plans"):
            logger.info("Migrating budget_plans...")
            rows = await src.fetch(
                "SELECT id, account_id, name, is_active, distribution, "
                "created_at, updated_at FROM budget_plans"
            )
            count = 0
            for row in rows:
                r = _normalize_row(row)
                try:
                    dist = r["distribution"]
                    if isinstance(dist, str):
                        dist = json.loads(dist)
                    result = await dst.execute(
                        "INSERT INTO copilot.budget_plans "
                        "(id, account_id, name, is_active, distribution, "
                        "created_at, updated_at) "
                        "VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7) "
                        "ON CONFLICT DO NOTHING",
                        r["id"], r["account_id"], r["name"], r["is_active"],
                        json.dumps(dist) if dist else "{}",
                        r["created_at"], r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping budget_plans row: {e}")
            summary["budget_plans"] = count
            logger.info(f"  budget_plans: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping budget_plans migration (source table missing)")
            summary["budget_plans"] = 0

        # -------------------------------------------------------------------
        # 3. agents_def
        # -------------------------------------------------------------------
        if await _table_exists(src, "agents_def"):
            logger.info("Migrating agents_def...")
            rows = await src.fetch(
                "SELECT agent_id, name, description, prompt, categories, tags, "
                "status, provider, account_id, created_at, updated_at "
                "FROM agents_def"
            )
            count = 0
            for row in rows:
                r = _normalize_row(row)
                try:
                    cats = r["categories"]
                    if isinstance(cats, str):
                        cats = json.loads(cats)
                    result = await dst.execute(
                        "INSERT INTO copilot.agents_def "
                        "(agent_id, name, description, prompt, categories, tags, "
                        "status, provider, account_id, created_at, updated_at) "
                        "VALUES ($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9,$10,$11) "
                        "ON CONFLICT DO NOTHING",
                        r["agent_id"], r["name"], r["description"], r["prompt"],
                        json.dumps(cats) if cats else "{}",
                        r["tags"] or [],
                        r["status"], r["provider"], r["account_id"],
                        r["created_at"], r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping agents_def row: {e}")
            summary["agents_def"] = count
            logger.info(f"  agents_def: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping agents_def migration (source table missing)")
            summary["agents_def"] = 0

        # -------------------------------------------------------------------
        # 4. agent_groups
        # -------------------------------------------------------------------
        if await _table_exists(src, "agent_groups"):
            logger.info("Migrating agent_groups...")
            rows = await src.fetch(
                "SELECT id, group_code, name, description, group_type, metadata, "
                "status, created_at, updated_at FROM agent_groups"
            )
            count = 0
            for row in rows:
                r = _normalize_row(row)
                try:
                    meta = r["metadata"]
                    if isinstance(meta, str):
                        meta = json.loads(meta)
                    account_id = (meta or {}).get("account_id") if meta else None
                    result = await dst.execute(
                        "INSERT INTO copilot.agent_groups "
                        "(id, account_id, group_code, name, description, "
                        "group_type, status, created_at, updated_at) "
                        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) "
                        "ON CONFLICT DO NOTHING",
                        r["id"], account_id, r["group_code"], r["name"],
                        r["description"], r["group_type"], r["status"],
                        r["created_at"], r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping agent_groups row: {e}")
            summary["agent_groups"] = count
            logger.info(f"  agent_groups: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping agent_groups migration (source table missing)")
            summary["agent_groups"] = 0

        # -------------------------------------------------------------------
        # 5. agent_group_members
        # -------------------------------------------------------------------
        if await _table_exists(src, "agent_group_members"):
            logger.info("Migrating agent_group_members...")
            rows = await src.fetch(
                "SELECT id, group_id, agent_id, display_order, created_at "
                "FROM agent_group_members"
            )
            count = 0
            for row in rows:
                r = _normalize_row(row)
                try:
                    result = await dst.execute(
                        "INSERT INTO copilot.agent_group_members "
                        "(id, group_id, agent_id, display_order, created_at) "
                        "VALUES ($1,$2,$3,$4,$5) "
                        "ON CONFLICT DO NOTHING",
                        r["id"], r["group_id"], r["agent_id"],
                        r["display_order"], r["created_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping agent_group_members row: {e}")
            summary["agent_group_members"] = count
            logger.info(f"  agent_group_members: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping agent_group_members migration (source table missing)")
            summary["agent_group_members"] = 0

        # -------------------------------------------------------------------
        # 6. marketplace_items (from agent_marketplace)
        # -------------------------------------------------------------------
        marketplace_table = await _first_existing_table(src, ["agent_marketplace", "marketplace_items"])
        if marketplace_table:
            logger.info(f"Migrating {marketplace_table} -> marketplace_items...")
            if marketplace_table == "agent_marketplace":
                rows = await src.fetch(
                    "SELECT marketplace_id, agent_id, title, short_description, "
                    "pricing_model, price, installation_count, rating_avg, "
                    "rating_count, is_featured, marketplace_status, "
                    "published_at, created_at, updated_at "
                    "FROM agent_marketplace"
                )
                count = 0
                for row in rows:
                    r = _normalize_row(row)
                    try:
                        result = await dst.execute(
                            "INSERT INTO copilot.marketplace_items "
                            "(marketplace_id, entity_id, entity_type, provider, title, "
                            "short_description, pricing_model, price, installation_count, "
                            "rating_avg, rating_count, is_featured, marketplace_status, "
                            "published_at, created_at, updated_at) "
                            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) "
                            "ON CONFLICT DO NOTHING",
                            r["marketplace_id"], str(r["agent_id"]), "agent",
                            "PLATFORM", r["title"],
                            r["short_description"],
                            r["pricing_model"], float(r["price"]) if r["price"] is not None else None,
                            r["installation_count"] or 0,
                            float(r["rating_avg"]) if r["rating_avg"] is not None else None,
                            r["rating_count"] or 0,
                            r["is_featured"] or False, r["marketplace_status"] or "draft",
                            r["published_at"], r["created_at"], r["updated_at"],
                        )
                        if result.endswith("1"):
                            count += 1
                    except Exception as e:
                        logger.warning(f"  Skipping marketplace_items row: {e}")
            else:
                rows = await src.fetch(
                    """
                    SELECT marketplace_id, entity_id, entity_type, provider, title, short_description,
                           pricing_model, price, installation_count, rating_avg, rating_count,
                           is_featured, marketplace_status, published_at, created_at, updated_at
                    FROM marketplace_items
                    """
                )
                count = 0
                for row in rows:
                    r = _normalize_row(row)
                    try:
                        result = await dst.execute(
                            "INSERT INTO copilot.marketplace_items "
                            "(marketplace_id, entity_id, entity_type, provider, title, short_description, "
                            "pricing_model, price, installation_count, rating_avg, rating_count, "
                            "is_featured, marketplace_status, published_at, created_at, updated_at) "
                            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) "
                            "ON CONFLICT DO NOTHING",
                            r["marketplace_id"], r["entity_id"], r["entity_type"], r["provider"],
                            r["title"], r["short_description"], r["pricing_model"],
                            float(r["price"]) if r["price"] is not None else None,
                            r["installation_count"] or 0,
                            float(r["rating_avg"]) if r["rating_avg"] is not None else None,
                            r["rating_count"] or 0,
                            r["is_featured"] or False, r["marketplace_status"] or "draft",
                            r["published_at"], r["created_at"], r["updated_at"],
                        )
                        if result.endswith("1"):
                            count += 1
                    except Exception as e:
                        logger.warning(f"  Skipping marketplace_items row: {e}")
            summary["marketplace_items"] = count
            logger.info(f"  marketplace_items: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping marketplace_items migration (source table missing)")
            summary["marketplace_items"] = 0

        # -------------------------------------------------------------------
        # 7. account_connections
        # -------------------------------------------------------------------
        if await _table_exists(src, "account_connections"):
            logger.info("Migrating account_connections...")
            rows = await src.fetch(
                "SELECT id, account_id, connection_type, name, description, "
                "connection_data, is_active, metadata, "
                "created_by, updated_by, created_at, updated_at "
                "FROM account_connections"
            )
            count = 0
            for row in rows:
                r = _normalize_row(row)
                try:
                    conn_data = r["connection_data"]
                    if isinstance(conn_data, str):
                        conn_data = json.loads(conn_data)
                    result = await dst.execute(
                        "INSERT INTO copilot.account_connections "
                        "(id, account_id, connection_type, name, description, "
                        "connection_data, is_active, metadata, created_by, updated_by, "
                        "created_at, updated_at) "
                        "VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7,$8::jsonb,$9,$10,$11,$12) "
                        "ON CONFLICT DO NOTHING",
                        r["id"], r["account_id"], r["connection_type"],
                        r["name"], r["description"],
                        json.dumps(conn_data) if conn_data else "{}",
                        r["is_active"], json.dumps(r["metadata"] or {}),
                        r["created_by"], r["updated_by"], r["created_at"], r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping account_connections row: {e}")
            summary["account_connections"] = count
            logger.info(f"  account_connections: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping account_connections migration (source table missing)")
            summary["account_connections"] = 0

        # -------------------------------------------------------------------
        # 8. guardrails_config
        # -------------------------------------------------------------------
        if await _table_exists(src, "guardrails_config"):
            logger.info("Migrating guardrails_config...")
            rows = await src.fetch(
                "SELECT id, account_id, guard_type, enabled, execution_order, "
                "action_on_fail, config, version, "
                "created_at, created_by, updated_at, updated_by "
                "FROM guardrails_config"
            )
            count = 0
            for row in rows:
                r = _normalize_row(row)
                try:
                    cfg = r["config"]
                    if isinstance(cfg, str):
                        cfg = json.loads(cfg)
                    result = await dst.execute(
                        "INSERT INTO copilot.guardrails_config "
                        "(id, account_id, guard_type, enabled, execution_order, "
                        "action_on_fail, config, version, created_by, updated_by, "
                        "created_at, updated_at) "
                        "VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9,$10,$11,$12) "
                        "ON CONFLICT DO NOTHING",
                        r["id"], r["account_id"], r["guard_type"],
                        r["enabled"], r["execution_order"], r["action_on_fail"],
                        json.dumps(cfg) if cfg else "{}",
                        r["version"], r["created_by"], r["updated_by"],
                        r["created_at"], r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping guardrails_config row: {e}")
            summary["guardrails_config"] = count
            logger.info(f"  guardrails_config: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping guardrails_config migration (source table missing)")
            summary["guardrails_config"] = 0

        # -------------------------------------------------------------------
        # 9. guardrails_custom_patterns
        # -------------------------------------------------------------------
        if await _table_exists(src, "guardrails_custom_patterns"):
            logger.info("Migrating guardrails_custom_patterns...")
            rows = await src.fetch(
                "SELECT id, account_id, guard_type, pattern_name, pattern_regex, "
                "pattern_type, action, enabled, severity, description, "
                "created_at, updated_at "
                "FROM guardrails_custom_patterns"
            )
            count = 0
            for row in rows:
                r = _normalize_row(row)
                try:
                    action_value = str(r.get("action") or "mask").strip().lower()
                    if action_value not in {"mask", "redact", "hash", "block"}:
                        action_value = "mask"
                    updated_at = r.get("updated_at") or r.get("created_at")
                    result = await dst.execute(
                        "INSERT INTO copilot.guardrails_custom_patterns "
                        "(id, account_id, guard_type, pattern_name, pattern_regex, "
                        "pattern_type, action, enabled, severity, description, "
                        "created_at, updated_at) "
                        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) "
                        "ON CONFLICT DO NOTHING",
                        r["id"], r["account_id"], r["guard_type"],
                        r["pattern_name"], r["pattern_regex"],
                        r["pattern_type"], action_value, r["enabled"], r["severity"],
                        r["description"],
                        r["created_at"], updated_at,
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping guardrails_custom_patterns row: {e}")
            summary["guardrails_custom_patterns"] = count
            logger.info(f"  guardrails_custom_patterns: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping guardrails_custom_patterns migration (source table missing)")
            summary["guardrails_custom_patterns"] = 0

        # -------------------------------------------------------------------
        # 10. guardrails_audit_log
        # -------------------------------------------------------------------
        if await _table_exists(src, "guardrails_audit_log"):
            logger.info("Migrating guardrails_audit_log...")
            rows = await src.fetch(
                "SELECT id, account_id, guard_type, action, old_config, "
                "new_config, changed_by, changed_at "
                "FROM guardrails_audit_log"
            )
            count = 0
            for row in rows:
                r = _normalize_row(row)
                try:
                    old_cfg = r["old_config"]
                    new_cfg = r["new_config"]
                    if isinstance(old_cfg, str):
                        old_cfg = json.loads(old_cfg)
                    if isinstance(new_cfg, str):
                        new_cfg = json.loads(new_cfg)
                    result = await dst.execute(
                        "INSERT INTO copilot.guardrails_audit_log "
                        "(id, account_id, guard_type, action, old_config, "
                        "new_config, changed_by, changed_at) "
                        "VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7,$8) "
                        "ON CONFLICT DO NOTHING",
                        r["id"], r["account_id"], r["guard_type"], r["action"],
                        json.dumps(old_cfg) if old_cfg else None,
                        json.dumps(new_cfg) if new_cfg else None,
                        r["changed_by"], r["changed_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping guardrails_audit_log row: {e}")
            summary["guardrails_audit_log"] = count
            logger.info(f"  guardrails_audit_log: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping guardrails_audit_log migration (source table missing)")
            summary["guardrails_audit_log"] = 0

        # -------------------------------------------------------------------
        # 11. users (account-scoped from account_memberships + users)
        # -------------------------------------------------------------------
        if await _table_exists(src, "account_memberships") and await _table_exists(src, "users"):
            logger.info("Migrating account-scoped users...")
            rows = await src.fetch(
                """
                SELECT
                    am.account_id,
                    u.id AS user_id,
                    u.email,
                    u.name,
                    u.profile_image,
                    COALESCE(u.is_active, true) AS is_active,
                    COALESCE(am.created_at, u.created_at, now()) AS created_at,
                    COALESCE(am.updated_at, u.updated_at, now()) AS updated_at
                FROM account_memberships am
                JOIN users u ON u.id = am.user_id
                """
            )
            count = 0
            for r in rows:
                try:
                    scoped_id = _scoped_user_id(str(r["account_id"]), str(r["user_id"]))
                    result = await dst.execute(
                        """
                        INSERT INTO copilot.users
                        (id, account_id, email, name, profile_image, is_active, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        scoped_id,
                        str(r["account_id"]),
                        (r["email"] or "").strip().lower(),
                        r["name"] or (r["email"] or "User"),
                        r["profile_image"],
                        bool(r["is_active"]),
                        r["created_at"],
                        r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping copilot.users row: {e}")
            summary["users"] = count
            logger.info(f"  users: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping users migration (source tables missing)")
            summary["users"] = 0

        # -------------------------------------------------------------------
        # 12. groups
        # -------------------------------------------------------------------
        if await _table_exists(src, "groups"):
            logger.info("Migrating groups...")
            rows = await src.fetch(
                """
                SELECT id, account_id, name, description, is_default,
                       owner_id, contact_email, created_by, updated_by, created_at, updated_at
                FROM groups
                """
            )
            count = 0
            for r in rows:
                try:
                    account_id = str(r["account_id"])
                    owner_id = (
                        _scoped_user_id(account_id, str(r["owner_id"]))
                        if r.get("owner_id")
                        else None
                    )
                    result = await dst.execute(
                        """
                        INSERT INTO copilot.groups
                        (id, account_id, name, description, is_default, owner_id, contact_email,
                         created_by, updated_by, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        r["id"],
                        account_id,
                        r["name"],
                        r["description"],
                        bool(r["is_default"] or False),
                        owner_id,
                        r["contact_email"],
                        str(r["created_by"]) if r["created_by"] else None,
                        str(r["updated_by"]) if r["updated_by"] else None,
                        r["created_at"],
                        r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping copilot.groups row: {e}")
            summary["groups"] = count
            logger.info(f"  groups: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping groups migration (source table missing)")
            summary["groups"] = 0

        # -------------------------------------------------------------------
        # 13. teams
        # -------------------------------------------------------------------
        if await _table_exists(src, "teams") and await _table_exists(src, "groups"):
            logger.info("Migrating teams...")
            rows = await src.fetch(
                """
                SELECT t.id, g.account_id, t.group_id, t.name, t.description, t.is_default,
                       t.owner_id, t.contact_email, t.created_by, t.updated_by, t.created_at, t.updated_at
                FROM teams t
                JOIN groups g ON g.id = t.group_id
                """
            )
            count = 0
            for r in rows:
                try:
                    account_id = str(r["account_id"])
                    owner_id = (
                        _scoped_user_id(account_id, str(r["owner_id"]))
                        if r.get("owner_id")
                        else None
                    )
                    result = await dst.execute(
                        """
                        INSERT INTO copilot.teams
                        (id, account_id, group_id, name, description, is_default, owner_id, contact_email,
                         created_by, updated_by, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        r["id"],
                        account_id,
                        r["group_id"],
                        r["name"],
                        r["description"],
                        bool(r["is_default"] or False),
                        owner_id,
                        r["contact_email"],
                        str(r["created_by"]) if r["created_by"] else None,
                        str(r["updated_by"]) if r["updated_by"] else None,
                        r["created_at"],
                        r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping copilot.teams row: {e}")
            summary["teams"] = count
            logger.info(f"  teams: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping teams migration (source tables missing)")
            summary["teams"] = 0

        # -------------------------------------------------------------------
        # 14. account_memberships
        # -------------------------------------------------------------------
        if await _table_exists(src, "account_memberships"):
            logger.info("Migrating account_memberships...")
            has_team_id = await _column_exists(src, "account_memberships", "team_id")
            team_id_sql = "team_id" if has_team_id else "NULL::uuid AS team_id"
            rows = await src.fetch(
                f"""
                SELECT account_id, user_id, app_role, is_active, {team_id_sql},
                       joined_at, last_active_at, tenant_preferences, created_at, updated_at
                FROM account_memberships
                """
            )
            count = 0
            role_map = {"OWNER": "ADMIN", "SUPER_ADMIN": "ADMIN"}
            for r in rows:
                try:
                    account_id = str(r["account_id"])
                    source_user_id = str(r["user_id"])
                    target_user_id = _scoped_user_id(account_id, source_user_id)
                    role = str(r["app_role"] or "USER").upper()
                    role = role_map.get(role, role)
                    if role not in {"ADMIN", "USER", "GUEST", "MEMBER", "VIEWER"}:
                        role = "USER"
                    membership_id = str(
                        uuid.uuid5(_USER_SCOPE_NAMESPACE, f"membership:{account_id}:{source_user_id}")
                    )
                    last_active_at = (
                        r.get("last_active_at")
                        or r.get("joined_at")
                        or r.get("updated_at")
                        or r.get("created_at")
                    )
                    result = await dst.execute(
                        """
                        INSERT INTO copilot.account_memberships
                        (id, account_id, user_id, app_role, team_id, is_active, joined_at, last_active_at,
                         tenant_preferences, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11)
                        ON CONFLICT (account_id, user_id) DO NOTHING
                        """,
                        membership_id,
                        account_id,
                        target_user_id,
                        role,
                        r["team_id"],
                        bool(r["is_active"] if r["is_active"] is not None else True),
                        r["joined_at"],
                        last_active_at,
                        json.dumps(r["tenant_preferences"] or {}),
                        r["created_at"],
                        r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping copilot.account_memberships row: {e}")
            summary["account_memberships"] = count
            logger.info(f"  account_memberships: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping account_memberships migration (source table missing)")
            summary["account_memberships"] = 0

        # -------------------------------------------------------------------
        # 15. user_invites (supports user_invites / userinvites)
        # -------------------------------------------------------------------
        invites_table = await _first_existing_table(src, ["user_invites", "userinvites"])
        if invites_table:
            logger.info(f"Migrating {invites_table} -> copilot.user_invites...")
            has_role_col = await _column_exists(src, invites_table, "role")
            role_select = "role" if has_role_col else "NULL::text AS role"
            rows = await src.fetch(
                f"""
                SELECT id, account_id, email, {role_select}, role_id, workspace_id,
                       status, token, invitation_data, created_by, accepted_by,
                       accepted_at, expires_at, created_at, updated_at
                FROM {invites_table}
                """
            )
            count = 0
            role_map = {"OWNER": "ADMIN", "SUPER_ADMIN": "ADMIN"}
            for r in rows:
                try:
                    invite_data = r["invitation_data"]
                    if isinstance(invite_data, str):
                        try:
                            invite_data = json.loads(invite_data)
                        except Exception:
                            invite_data = {}
                    role = str(
                        r["role"]
                        or (invite_data or {}).get("app_role")
                        or (invite_data or {}).get("role")
                        or "USER"
                    ).upper()
                    role = role_map.get(role, role)
                    if role not in {"ADMIN", "USER", "GUEST", "MEMBER", "VIEWER"}:
                        role = "USER"

                    status = str(r["status"] or "PENDING").upper()
                    if status not in {"PENDING", "ACCEPTED", "DECLINED", "EXPIRED", "CANCELLED"}:
                        status = "PENDING"

                    result = await dst.execute(
                        """
                        INSERT INTO copilot.user_invites
                        (id, account_id, email, role, role_id, workspace_id, status, token,
                         invitation_data, created_by, accepted_by, accepted_at, expires_at,
                         created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11,$12,$13,$14,$15)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        r["id"],
                        str(r["account_id"]),
                        str(r["email"] or "").strip().lower(),
                        role,
                        str(r["role_id"]) if r["role_id"] else None,
                        str(r["workspace_id"]) if r["workspace_id"] else None,
                        status,
                        r["token"],
                        json.dumps(invite_data or {}),
                        str(r["created_by"]) if r["created_by"] else None,
                        str(r["accepted_by"]) if r["accepted_by"] else None,
                        r["accepted_at"],
                        r["expires_at"],
                        r["created_at"],
                        r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping copilot.user_invites row: {e}")
            summary["user_invites"] = count
            logger.info(f"  user_invites: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping user_invites migration (source table missing)")
            summary["user_invites"] = 0

        # -------------------------------------------------------------------
        # 16. notification_templates (prefer account-scoped source table)
        # -------------------------------------------------------------------
        nt_table = await _first_existing_table(
            src, ["account_notification_templates", "notificationtemplates"]
        )
        if nt_table:
            has_account_id = await _column_exists(src, nt_table, "account_id")
            if not has_account_id:
                logger.info(
                    f"Skipping {nt_table} migration because account_id column is missing."
                )
                summary["notification_templates"] = 0
            else:
                logger.info(f"Migrating {nt_table} -> copilot.notification_templates...")
                rows = await src.fetch(
                    f"""
                    SELECT id, account_id, template_id, title_line, template_content, event_id,
                           type, created_by, updated_by, created_at, updated_at
                    FROM {nt_table}
                    WHERE account_id IS NOT NULL
                    """
                )
                count = 0
                for r in rows:
                    try:
                        n_type = str(r["type"] or "EMAIL").upper()
                        if n_type not in {"EMAIL", "PUSH", "SMS", "IN_APP"}:
                            n_type = "EMAIL"
                        result = await dst.execute(
                            """
                            INSERT INTO copilot.notification_templates
                            (id, account_id, template_id, title_line, template_content, event_id,
                             type, created_by, updated_by, created_at, updated_at)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                            ON CONFLICT (id) DO NOTHING
                            """,
                            r["id"],
                            str(r["account_id"]),
                            r["template_id"],
                            r["title_line"] or "",
                            r["template_content"] or "",
                            r["event_id"],
                            n_type,
                            str(r["created_by"]) if r["created_by"] else None,
                            str(r["updated_by"]) if r["updated_by"] else None,
                            r["created_at"],
                            r["updated_at"],
                        )
                        if result.endswith("1"):
                            count += 1
                    except Exception as e:
                        logger.warning(f"  Skipping copilot.notification_templates row: {e}")
                summary["notification_templates"] = count
                logger.info(f"  notification_templates: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping notification_templates migration (source table missing)")
            summary["notification_templates"] = 0

        # -------------------------------------------------------------------
        # 17. support_tickets (supports support_tickets / supporttickets)
        # -------------------------------------------------------------------
        st_table = await _first_existing_table(src, ["support_tickets", "supporttickets"])
        if st_table:
            logger.info(f"Migrating {st_table} -> copilot.support_tickets...")
            rows = await src.fetch(
                f"""
                SELECT id, account_id, user_profile_id, subject, description, status, priority,
                       assigned_to, created_by, updated_by, created_at, updated_at
                FROM {st_table}
                """
            )
            count = 0
            for r in rows:
                try:
                    status = str(r["status"] or "OPEN").upper()
                    priority = str(r["priority"] or "MEDIUM").upper()
                    if status not in {"OPEN", "IN_PROGRESS", "PENDING", "RESOLVED", "CLOSED", "CANCELLED"}:
                        status = "OPEN"
                    if priority not in {"LOW", "MEDIUM", "URGENT", "IMPORTANT"}:
                        priority = "MEDIUM"
                    desc = r["description"]
                    if isinstance(desc, (dict, list)):
                        desc = json.dumps(desc)
                    elif desc is None:
                        desc = ""
                    else:
                        desc = str(desc)

                    result = await dst.execute(
                        """
                        INSERT INTO copilot.support_tickets
                        (id, account_id, user_profile_id, subject, description, status, priority,
                         assigned_to, created_by, updated_by, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        r["id"],
                        str(r["account_id"]),
                        str(r["user_profile_id"]) if r["user_profile_id"] else None,
                        r["subject"] or "Support Request",
                        desc,
                        status,
                        priority,
                        str(r["assigned_to"]) if r["assigned_to"] else None,
                        str(r["created_by"]) if r["created_by"] else None,
                        str(r["updated_by"]) if r["updated_by"] else None,
                        r["created_at"],
                        r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping copilot.support_tickets row: {e}")
            summary["support_tickets"] = count
            logger.info(f"  support_tickets: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping support_tickets migration (source table missing)")
            summary["support_tickets"] = 0

        # -------------------------------------------------------------------
        # 18. model_catalog (from config_models / models / copilot_models)
        # -------------------------------------------------------------------
        model_table = await _first_existing_table(src, ["config_models", "models", "copilot_models"])
        if model_table:
            logger.info(f"Migrating {model_table} -> copilot.model_catalog...")
            rows = await src.fetch(f"SELECT * FROM {model_table}")
            count = 0

            credits_factor = _safe_float(os.getenv("CREDITS_FACTOR"), default=5.0)
            if credits_factor <= 0:
                credits_factor = 5.0

            for row in rows:
                try:
                    r = _normalize_row(row)

                    # Preferred mapping for config_models consolidated schema
                    if model_table == "config_models":
                        model_name = (
                            r.get("id")
                            or r.get("model_name")
                            or r.get("model")
                            or r.get("deployment_name")
                        )
                        deployment_name = r.get("deployment_name")
                        capability = r.get("capability")
                        provider = r.get("provider_id") or r.get("provider") or r.get("vendor")
                        display_name = r.get("display_name") or r.get("name") or model_name
                        upstream_model_name = (
                            r.get("upstream_model_name")
                            or r.get("target_model")
                            or deployment_name
                            or model_name
                        )

                        # config_models stores USD costs per million tokens
                        input_cost_per_million = _safe_float(r.get("input_cost_per_million"), default=0.0)
                        output_cost_per_million = _safe_float(r.get("output_cost_per_million"), default=0.0)
                        # Single catalog field uses blended average credits/1k while preserving
                        # directional pricing in metadata for precise downstream usage.
                        blended_cost_per_million = (
                            (input_cost_per_million + output_cost_per_million) / 2.0
                        )
                        credits_per_1k_tokens = (blended_cost_per_million / 1000.0) * credits_factor

                        metadata = {
                            "legacy_source_table": model_table,
                            "legacy_row": r,
                            "pricing": {
                                "credits_factor": credits_factor,
                                "input_cost_per_million_usd": input_cost_per_million,
                                "output_cost_per_million_usd": output_cost_per_million,
                                "input_credits_per_1k_tokens": (input_cost_per_million / 1000.0) * credits_factor,
                                "output_credits_per_1k_tokens": (output_cost_per_million / 1000.0) * credits_factor,
                                "blended_credits_per_1k_tokens": credits_per_1k_tokens,
                            },
                            "provider_id": provider,
                            "deployment_name": deployment_name,
                            "capability": capability,
                            "content_capabilities": r.get("content_capabilities"),
                            "extra_body": r.get("extra_body"),
                            "sort_order": r.get("sort_order"),
                        }
                    else:
                        # Generic fallback for older/other model tables
                        model_name = (
                            r.get("model_name")
                            or r.get("model")
                            or r.get("slug")
                            or r.get("name")
                            or r.get("model_id")
                            or r.get("id")
                        )
                        provider = r.get("provider") or r.get("vendor")
                        if not provider and model_name and "/" in str(model_name):
                            provider = str(model_name).split("/", 1)[0]

                        display_name = (
                            r.get("display_name")
                            or r.get("title")
                            or r.get("name")
                            or model_name
                        )
                        upstream_model_name = (
                            r.get("upstream_model_name")
                            or r.get("target_model")
                            or r.get("deployment_name")
                            or r.get("model")
                            or model_name
                        )
                        credits_raw = (
                            r.get("credits_per_1k_tokens")
                            or r.get("credit_per_1k")
                            or r.get("cost_per_1k")
                            or r.get("price_per_1k")
                            or 0
                        )
                        credits_per_1k_tokens = _safe_float(credits_raw, default=0.0)
                        metadata = {"legacy_source_table": model_table, "legacy_row": r}

                    model_name = str(model_name or "").strip()
                    if not model_name:
                        continue

                    raw_is_active = r.get("is_active")
                    if raw_is_active is None:
                        raw_is_active = r.get("enabled")
                    if raw_is_active is None:
                        status = str(r.get("status") or "").strip().lower()
                        raw_is_active = status not in {"inactive", "disabled", "archived"}
                    is_active = _to_bool(raw_is_active, default=True)

                    # copilot.model_catalog.id is UUID; derive deterministic UUID from model_name
                    row_id = str(uuid.uuid5(_MODEL_CATALOG_NAMESPACE, model_name.lower()))

                    insert_result = await dst.execute(
                        """
                        INSERT INTO copilot.model_catalog
                        (id, model_name, display_name, provider, source, upstream_model_name,
                         credits_per_1k_tokens, is_active, metadata, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10,$11)
                        ON CONFLICT DO NOTHING
                        """,
                        row_id,
                        model_name,
                        str(display_name or model_name),
                        str(provider) if provider else None,
                        "legacy_backfill",
                        str(upstream_model_name or model_name),
                        credits_per_1k_tokens,
                        is_active,
                        json.dumps(metadata, default=str),
                        r.get("created_at"),
                        r.get("updated_at"),
                    )
                    update_result = await dst.execute(
                        """
                        UPDATE copilot.model_catalog
                           SET display_name = $2,
                               provider = $3,
                               source = $4,
                               upstream_model_name = $5,
                               credits_per_1k_tokens = $6,
                               is_active = $7,
                               metadata = $8::jsonb,
                               updated_at = COALESCE($9, NOW())
                         WHERE lower(model_name) = lower($1)
                        """,
                        model_name,
                        str(display_name or model_name),
                        str(provider) if provider else None,
                        "legacy_backfill",
                        str(upstream_model_name or model_name),
                        credits_per_1k_tokens,
                        is_active,
                        json.dumps(metadata, default=str),
                        r.get("updated_at"),
                    )
                    if insert_result.startswith("INSERT") or update_result.endswith(" 1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping copilot.model_catalog row: {e}")
            summary["model_catalog"] = count
            logger.info(f"  model_catalog: {count}/{len(rows)} rows upserted")
        else:
            logger.info("Skipping model_catalog migration (source table missing)")
            summary["model_catalog"] = 0

        # -------------------------------------------------------------------
        # 19. integration_catalog (from integrations_def)
        # -------------------------------------------------------------------
        if await _table_exists(src, "integrations_def"):
            logger.info("Migrating integrations_def -> copilot.integration_catalog...")
            rows = await src.fetch(
                """
                SELECT id, name, description, toolkit, auth_config_id, icon, color, enabled,
                       created_at, updated_at
                FROM integrations_def
                """
            )
            count = 0
            for r in rows:
                try:
                    key = str(r["id"] or "").strip()
                    if not key:
                        continue
                    result = await dst.execute(
                        """
                        INSERT INTO copilot.integration_catalog
                        (id, integration_key, provider, name, description, toolkit, auth_config_id,
                         icon, color, is_active, metadata, created_at, updated_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12,$13)
                        ON CONFLICT DO NOTHING
                        """,
                        str(uuid.uuid4()),
                        key,
                        "composio",
                        str(r["name"] or key),
                        r["description"],
                        r["toolkit"],
                        r["auth_config_id"],
                        r["icon"],
                        r["color"],
                        bool(r["enabled"] if r["enabled"] is not None else True),
                        json.dumps({"legacy_source_table": "integrations_def"}),
                        r["created_at"],
                        r["updated_at"],
                    )
                    if result.endswith("1"):
                        count += 1
                except Exception as e:
                    logger.warning(f"  Skipping copilot.integration_catalog row: {e}")
            summary["integration_catalog"] = count
            logger.info(f"  integration_catalog: {count}/{len(rows)} rows")
        else:
            logger.info("Skipping integration_catalog migration (source table missing)")
            summary["integration_catalog"] = 0

    finally:
        await src.close()
        await dst.close()

    # Print summary
    logger.info("")
    logger.info("=" * 50)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 50)
    total = 0
    for table, cnt in summary.items():
        logger.info(f"  {table:40s} {cnt:6d} rows")
        total += cnt
    logger.info(f"  {'TOTAL':40s} {total:6d} rows")
    logger.info("=" * 50)
    logger.info("Migration complete. Re-run is safe (ON CONFLICT DO NOTHING).")


def main():
    asyncio.run(run_migration())


if __name__ == "__main__":
    main()
