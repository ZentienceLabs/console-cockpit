"""
Migrate agent-related data from alchemi-web and alchemi-ai into console-cockpit.

Tables:
  agents_def          -> Alchemi_AgentDefTable         (DEDUP: web canonical)
  agent_groups        -> Alchemi_AgentGroupTable
  agent_group_members -> Alchemi_AgentGroupMemberTable
  agent_marketplace   -> Alchemi_AgentMarketplaceTable (web only)

Deduplication:
  agents_def exists in BOTH alchemi-web and alchemi-ai databases.
  alchemi-web is canonical — it is inserted first, and alchemi-ai rows
  are inserted second with ON CONFLICT DO NOTHING so web wins on conflict.

Idempotent: safe to re-run (all inserts use ON CONFLICT DO NOTHING).
"""

import asyncio
import sys

sys.path.insert(0, "/workspaces/console-cockpit/scripts/migrate")
from common import MigrationRunner, migrate_table, migrate_with_dedup, setup_logging, logger


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

# agents_def — full column set from alchemi-web (canonical)
WEB_AGENTS_DEF_SOURCE_COLS = [
    "agent_id",
    "name",
    "description",
    "prompt",
    "page",
    "categories",
    "tags",
    "builtin_tools",
    "tools_mcp_ids",
    "tools_openapi_ids",
    "links",
    "is_singleton",
    "is_non_conversational",
    "status",
    "availability",
    "provider",
    "account_id",
    "created_at",
    "updated_at",
]

AGENTS_DEF_DEST_COLS = [
    "agent_id",  # PK in Prisma schema (maps from source agent_id)
    "name",
    "description",
    "prompt",
    "page",
    "categories",
    "tags",
    "builtin_tools",
    "tools_mcp_ids",
    "tools_openapi_ids",
    "links",
    "is_singleton",
    "is_non_conversational",
    "status",
    "availability",
    "provider",
    "account_id",
    "created_at",
    "updated_at",
]

# agents_def — reduced column set that alchemi-ai may have
AI_AGENTS_DEF_SOURCE_COLS = [
    "agent_id",
    "name",
    "description",
    "prompt",
    "page",
    "categories",
    "tags",
    "builtin_tools",
    "tools_mcp_ids",
    "links",
    "is_singleton",
    "status",
    "availability",
]

# agent_groups
AGENT_GROUPS_COLS = [
    "id",
    "group_code",
    "name",
    "description",
    "group_type",
    "metadata",
    "status",
    "account_id",
    "created_at",
    "updated_at",
]

# agent_group_members
AGENT_GROUP_MEMBERS_COLS = [
    "id",
    "group_id",
    "agent_id",
    "display_order",
    "metadata",
    "created_at",
    "updated_at",
]

# agent_marketplace
AGENT_MARKETPLACE_COLS = [
    "id",
    "agent_id",
    "listing_status",
    "listing_data",
    "account_id",
    "created_at",
    "updated_at",
]


# ---------------------------------------------------------------------------
# Row transform: alchemi-ai agents_def → dest (pad missing columns)
# ---------------------------------------------------------------------------

def _transform_ai_agent_row(row: dict) -> tuple:
    """
    Transform an alchemi-ai agents_def row into a tuple matching
    AGENTS_DEF_DEST_COLS.  The AI source may lack several columns that
    exist in the web source; we fill them with sensible defaults.
    """
    return (
        row.get("agent_id"),
        row.get("name"),
        row.get("description"),
        row.get("prompt"),
        row.get("page"),
        row.get("categories", "{}"),
        row.get("tags", []),
        row.get("builtin_tools", []),
        row.get("tools_mcp_ids", []),
        row.get("tools_openapi_ids", []),       # not in AI source
        row.get("links", "{}"),
        row.get("is_singleton", False),
        row.get("is_non_conversational", False), # not in AI source
        row.get("status", "active"),
        row.get("availability", ["platform"]),
        row.get("provider", "PLATFORM"),         # not in AI source
        row.get("account_id"),                   # not in AI source
        row.get("created_at"),
        row.get("updated_at"),
    )


# ---------------------------------------------------------------------------
# Build SELECT helpers
# ---------------------------------------------------------------------------

def _select_query(table: str, columns: list[str]) -> str:
    """Build a quoted SELECT ... FROM ... ORDER BY 1 query."""
    col_str = ", ".join(f'"{c}"' for c in columns)
    return f'SELECT {col_str} FROM "{table}" ORDER BY 1'


# ---------------------------------------------------------------------------
# Main migration
# ---------------------------------------------------------------------------

async def migrate_agents() -> None:
    async with MigrationRunner("agents", needs_web=True, needs_ai=True) as runner:
        dest = runner.dest
        if dest is None:
            logger.error("Cannot connect to destination database — aborting.")
            return

        # ---------------------------------------------------------------
        # 1. agents_def → Alchemi_AgentDefTable  (DEDUP: web first)
        # ---------------------------------------------------------------
        logger.info("Migrating agents_def -> Alchemi_AgentDefTable (dedup)")

        sources: list[tuple] = []

        # Web source (canonical — inserted first)
        if runner.web:
            web_query = _select_query("agents_def", WEB_AGENTS_DEF_SOURCE_COLS)
            sources.append((runner.web, web_query, "alchemi-web"))
        else:
            logger.warning("alchemi-web not available; skipping canonical source for agents_def")

        # AI source (secondary — ON CONFLICT DO NOTHING)
        if runner.ai:
            try:
                from common import table_exists

                if await table_exists(runner.ai, "agents_def"):
                    # Detect which columns the AI table actually has
                    ai_col_info = await runner.ai.fetch(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_name = 'agents_def'
                        ORDER BY ordinal_position
                        """
                    )
                    ai_available_cols = {r["column_name"] for r in ai_col_info}

                    # Use only columns that actually exist in the AI table
                    ai_select_cols = [
                        c for c in AI_AGENTS_DEF_SOURCE_COLS if c in ai_available_cols
                    ]
                    if "agent_id" in ai_available_cols and ai_select_cols:
                        ai_query = _select_query("agents_def", ai_select_cols)
                        sources.append((runner.ai, ai_query, "alchemi-ai"))
                        logger.info(
                            f"  alchemi-ai agents_def columns detected: {ai_select_cols}"
                        )
                    else:
                        logger.warning(
                            "  alchemi-ai agents_def lacks agent_id column; skipping"
                        )
                else:
                    logger.info("  alchemi-ai does not have agents_def table; skipping")
            except Exception as exc:
                logger.warning(f"  Could not inspect alchemi-ai agents_def: {exc}")

        if sources:
            await migrate_with_dedup(
                sources=sources,
                dest=dest,
                dest_table="Alchemi_AgentDefTable",
                columns=AGENTS_DEF_DEST_COLS,
                dedup_key=["agent_id"],
                transform_row=_transform_ai_agent_row if runner.ai else None,
            )
        else:
            logger.warning("No sources available for agents_def — nothing to migrate")

        # ---------------------------------------------------------------
        # 2. agent_groups → Alchemi_AgentGroupTable
        # ---------------------------------------------------------------
        logger.info("Migrating agent_groups -> Alchemi_AgentGroupTable")

        if runner.web:
            await migrate_table(
                source=runner.web,
                dest=dest,
                source_table="agent_groups",
                dest_table="Alchemi_AgentGroupTable",
                columns=AGENT_GROUPS_COLS,
                conflict_columns=["group_code"],
            )
        else:
            logger.warning("alchemi-web not available; skipping agent_groups")

        # ---------------------------------------------------------------
        # 3. agent_group_members → Alchemi_AgentGroupMemberTable
        # ---------------------------------------------------------------
        logger.info("Migrating agent_group_members -> Alchemi_AgentGroupMemberTable")

        if runner.web:
            await migrate_table(
                source=runner.web,
                dest=dest,
                source_table="agent_group_members",
                dest_table="Alchemi_AgentGroupMemberTable",
                columns=AGENT_GROUP_MEMBERS_COLS,
                conflict_columns=["group_id", "agent_id"],
            )
        else:
            logger.warning("alchemi-web not available; skipping agent_group_members")

        # ---------------------------------------------------------------
        # 4. agent_marketplace → Alchemi_AgentMarketplaceTable (web only)
        # ---------------------------------------------------------------
        logger.info("Migrating agent_marketplace -> Alchemi_AgentMarketplaceTable")

        if runner.web:
            await migrate_table(
                source=runner.web,
                dest=dest,
                source_table="agent_marketplace",
                dest_table="Alchemi_AgentMarketplaceTable",
                columns=AGENT_MARKETPLACE_COLS,
                conflict_columns=["id"],
            )
        else:
            logger.warning("alchemi-web not available; skipping agent_marketplace")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(migrate_agents())
