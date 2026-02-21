"""
Migrate cost_tracking from alchemi-web and alchemi-ai into console-cockpit.

DEDUPLICATION: cost_tracking exists in BOTH databases.
alchemi-ai is canonical (has thread_id).

Strategy:
  1. Insert all rows from alchemi-ai FIRST (canonical source -- has thread_id).
  2. Insert rows from alchemi-web SECOND, skipping any row whose natural key
     (workspace_id, account_id, user_id, model, tool, cost, created_at) already
     exists in the destination from Phase 1.
  3. Destination uses autoincrement id; source IDs are NOT preserved.

Dedup approach:
  - A temporary staging table on the dest connection receives each batch.
  - An INSERT ... SELECT ... WHERE NOT EXISTS transfers only genuinely new
    rows from the staging table into the destination.
  - A temporary composite index on the dedup-key columns keeps the
    NOT EXISTS check fast even for millions of rows.
  - account_id (nullable) is compared with IS NOT DISTINCT FROM to properly
    handle NULL values, unlike a UNIQUE index which treats NULLs as distinct.

Idempotent: safe to re-run.  Phase 1 re-runs skip rows already present;
Phase 2 re-runs skip rows that match on the natural key.
"""

import asyncio
import sys
import time
from typing import List

sys.path.insert(0, "/workspaces/console-cockpit/scripts/migrate")
from common import (
    MigrationRunner,
    setup_logging,
    logger,
    BATCH_SIZE,
    table_exists,
    get_row_count,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEST_TABLE = "Alchemi_CostTrackingTable"
SOURCE_TABLE = "cost_tracking"

# Every column written to the staging temp table (and, conditionally, to dest).
STAGING_COLUMNS: List[str] = [
    "workspace_id",
    "account_id",
    "user_id",
    "model",
    "tool",
    "cost",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "metadata",
    "thread_id",
    "created_at",
    "updated_at",
]

# Natural key used for cross-source deduplication.
DEDUP_KEY: List[str] = [
    "workspace_id",
    "account_id",
    "user_id",
    "model",
    "tool",
    "cost",
    "created_at",
]


# ---------------------------------------------------------------------------
# SQL templates
# ---------------------------------------------------------------------------

CREATE_STAGING_SQL = """
CREATE TEMP TABLE IF NOT EXISTS _cost_staging (
    workspace_id      TEXT        NOT NULL,
    account_id        TEXT,
    user_id           TEXT        NOT NULL,
    model             TEXT        NOT NULL,
    tool              TEXT        NOT NULL,
    cost              DOUBLE PRECISION NOT NULL,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    metadata          JSONB,
    thread_id         TEXT,
    created_at        TIMESTAMPTZ NOT NULL,
    updated_at        TIMESTAMPTZ
)
""".strip()

TRUNCATE_STAGING_SQL = "TRUNCATE _cost_staging"
DROP_STAGING_SQL = "DROP TABLE IF EXISTS _cost_staging"

# Non-unique index on the dest table to speed up the NOT EXISTS dedup check.
# Covers every non-nullable column in the natural key; account_id (nullable)
# is checked via IS NOT DISTINCT FROM as a residual filter.
CREATE_DEDUP_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS "_tmp_cost_dedup_idx"
ON "{dest}" ("workspace_id", "user_id", "model", "tool", "cost", "created_at")
""".strip().format(dest=DEST_TABLE)

DROP_DEDUP_INDEX_SQL = 'DROP INDEX IF EXISTS "_tmp_cost_dedup_idx"'


# ---------------------------------------------------------------------------
# Dynamic SQL builders
# ---------------------------------------------------------------------------


def _build_insert_from_staging_sql(include_updated_at: bool) -> str:
    """Return an INSERT ... SELECT ... WHERE NOT EXISTS statement that copies
    rows from ``_cost_staging`` into the destination, skipping any row whose
    natural key already exists in the destination.

    Uses IS NOT DISTINCT FROM for ``account_id`` so that two NULLs are
    treated as equal (unlike a plain ``=`` comparison).
    """

    if include_updated_at:
        dest_cols = (
            '"workspace_id", "account_id", "user_id", "model", "tool", "cost", '
            '"prompt_tokens", "completion_tokens", "total_tokens", "metadata", '
            '"thread_id", "created_at", "updated_at"'
        )
        staging_select = (
            "s.workspace_id, s.account_id, s.user_id, s.model, s.tool, s.cost, "
            "s.prompt_tokens, s.completion_tokens, s.total_tokens, s.metadata, "
            "s.thread_id, s.created_at, s.updated_at"
        )
    else:
        dest_cols = (
            '"workspace_id", "account_id", "user_id", "model", "tool", "cost", '
            '"prompt_tokens", "completion_tokens", "total_tokens", "metadata", '
            '"thread_id", "created_at"'
        )
        staging_select = (
            "s.workspace_id, s.account_id, s.user_id, s.model, s.tool, s.cost, "
            "s.prompt_tokens, s.completion_tokens, s.total_tokens, s.metadata, "
            "s.thread_id, s.created_at"
        )

    return f"""
INSERT INTO "{DEST_TABLE}" ({dest_cols})
SELECT {staging_select}
FROM _cost_staging s
WHERE NOT EXISTS (
    SELECT 1 FROM "{DEST_TABLE}" d
    WHERE d."workspace_id" = s.workspace_id
      AND d."user_id"      = s.user_id
      AND d."model"        = s.model
      AND d."tool"         = s.tool
      AND d."cost"         = s.cost
      AND d."created_at"   = s.created_at
      AND d."account_id" IS NOT DISTINCT FROM s.account_id
)
""".strip()


def _build_ai_source_query(has_updated_at: bool) -> str:
    """Build the SELECT for alchemi-ai (canonical -- includes thread_id)."""
    updated_at_expr = "updated_at" if has_updated_at else "created_at AS updated_at"
    return f"""
SELECT
    workspace_id, account_id, user_id, model, tool, cost,
    prompt_tokens, completion_tokens, total_tokens,
    metadata, thread_id, created_at,
    {updated_at_expr}
FROM {SOURCE_TABLE}
ORDER BY id
""".strip()


def _build_web_source_query() -> str:
    """Build the SELECT for alchemi-web (no thread_id, no updated_at)."""
    return f"""
SELECT
    workspace_id, account_id, user_id, model, tool, cost,
    prompt_tokens, completion_tokens, total_tokens,
    metadata,
    NULL::text AS thread_id,
    created_at,
    created_at AS updated_at
FROM {SOURCE_TABLE}
ORDER BY id
""".strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _column_exists(conn, table: str, column: str) -> bool:
    """Return True if *column* exists in *table*."""
    return bool(
        await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = $1 AND column_name = $2
            )
            """,
            table,
            column,
        )
    )


def _normalize_row(row) -> tuple:
    """Convert an asyncpg Record to a tuple aligned to STAGING_COLUMNS,
    coercing numeric types to avoid codec mismatches between source and
    staging table types."""
    d = dict(row)
    # cost: source may be Decimal; staging column is DOUBLE PRECISION.
    if d.get("cost") is not None:
        d["cost"] = float(d["cost"])
    # Token counts: ensure plain int (source might use bigint or numeric).
    for tok in ("prompt_tokens", "completion_tokens", "total_tokens"):
        v = d.get(tok)
        if v is not None:
            d[tok] = int(v)
    return tuple(d[c] for c in STAGING_COLUMNS)


# ---------------------------------------------------------------------------
# Core batch-migration loop
# ---------------------------------------------------------------------------


async def _migrate_source(
    *,
    source,
    dest,
    source_query: str,
    insert_from_staging_sql: str,
    label: str,
    batch_size: int = BATCH_SIZE,
) -> int:
    """Fetch rows from *source* in batches, stage them on *dest*, and insert
    only rows whose natural key is not already present in the destination.

    Returns the number of rows actually inserted into the destination.
    """
    staging_col_str = ", ".join(STAGING_COLUMNS)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(STAGING_COLUMNS)))
    staging_insert_sql = (
        f"INSERT INTO _cost_staging ({staging_col_str}) VALUES ({placeholders})"
    )

    total_inserted = 0
    total_processed = 0
    batch_num = 0
    offset = 0
    start = time.time()

    while True:
        batch_query = f"{source_query} LIMIT {batch_size} OFFSET {offset}"
        try:
            rows = await source.fetch(batch_query)
        except Exception as exc:
            logger.warning(f"  [{label}] query failed at offset {offset}: {exc}")
            break

        if not rows:
            break

        batch_num += 1
        total_processed += len(rows)

        # 1. Clear staging
        await dest.execute(TRUNCATE_STAGING_SQL)

        # 2. Load batch into staging
        values = [_normalize_row(r) for r in rows]
        try:
            await dest.executemany(staging_insert_sql, values)
        except Exception as exc:
            logger.error(
                f"  [{label}] executemany failed at offset {offset}: {exc}"
            )
            # Fall back to row-by-row to skip only the problematic rows.
            for i, val in enumerate(values):
                try:
                    await dest.execute(staging_insert_sql, *val)
                except Exception as row_err:
                    logger.warning(
                        f"  [{label}] skipping row {offset + i}: {row_err}"
                    )

        # 3. Dedup-insert from staging into destination
        try:
            tag = await dest.execute(insert_from_staging_sql)
            # tag is e.g. "INSERT 0 42"
            inserted = int(tag.split()[-1]) if tag else 0
            total_inserted += inserted
        except Exception as exc:
            logger.error(
                f"  [{label}] insert-from-staging failed at offset {offset}: {exc}"
            )

        # 4. Progress logging (every 10 batches and on the final batch)
        if batch_num % 10 == 0 or len(rows) < batch_size:
            elapsed = time.time() - start
            logger.info(
                f"  [{label}] {total_processed:,} processed, "
                f"{total_inserted:,} inserted ({elapsed:.1f}s)"
            )

        offset += batch_size
        if len(rows) < batch_size:
            break

    elapsed = time.time() - start
    logger.info(
        f"  [{label}] done: {total_processed:,} processed, "
        f"{total_inserted:,} inserted in {elapsed:.1f}s"
    )
    return total_inserted


# ---------------------------------------------------------------------------
# Top-level migration
# ---------------------------------------------------------------------------


async def migrate_cost_tracking() -> None:
    """Migrate cost_tracking from both alchemi-ai and alchemi-web into the
    console-cockpit destination, with cross-source deduplication."""

    async with MigrationRunner(
        "cost_tracking", needs_web=True, needs_ai=True
    ) as runner:
        if runner.dest is None:
            logger.error("Destination database connection unavailable")
            return

        if not await table_exists(runner.dest, DEST_TABLE):
            logger.error(f"Destination table {DEST_TABLE} does not exist")
            return

        # Detect optional updated_at column in dest (Prisma schema may or may
        # not include it yet).
        dest_has_updated_at = await _column_exists(
            runner.dest, DEST_TABLE, "updated_at"
        )
        if not dest_has_updated_at:
            logger.info(
                "Destination table does not have updated_at column; "
                "it will be omitted from inserts"
            )

        insert_from_staging = _build_insert_from_staging_sql(dest_has_updated_at)

        # Prepare staging infrastructure on the dest connection.
        await runner.dest.execute(CREATE_STAGING_SQL)
        await runner.dest.execute(DROP_DEDUP_INDEX_SQL)  # clean up any leftover
        logger.info("Creating temporary dedup index for performance...")
        await runner.dest.execute(CREATE_DEDUP_INDEX_SQL)

        grand_total = 0

        # ------------------------------------------------------------------
        # Phase 1: alchemi-ai  (canonical -- has thread_id)
        # ------------------------------------------------------------------
        logger.info(
            "--- Phase 1: alchemi-ai (canonical) -> %s ---", DEST_TABLE
        )
        if runner.ai is not None:
            if await table_exists(runner.ai, SOURCE_TABLE):
                ai_count = await get_row_count(runner.ai, SOURCE_TABLE)
                logger.info(f"  Source row count (alchemi-ai): {ai_count:,}")

                ai_has_updated_at = await _column_exists(
                    runner.ai, SOURCE_TABLE, "updated_at"
                )
                ai_query = _build_ai_source_query(ai_has_updated_at)

                inserted = await _migrate_source(
                    source=runner.ai,
                    dest=runner.dest,
                    source_query=ai_query,
                    insert_from_staging_sql=insert_from_staging,
                    label="alchemi-ai",
                )
                grand_total += inserted
            else:
                logger.warning(
                    "Source table %s not found in alchemi-ai", SOURCE_TABLE
                )
        else:
            logger.warning("Skipping alchemi-ai: connection unavailable")

        # ------------------------------------------------------------------
        # Phase 2: alchemi-web  (secondary -- no thread_id; dedup vs Phase 1)
        # ------------------------------------------------------------------
        logger.info(
            "--- Phase 2: alchemi-web (dedup) -> %s ---", DEST_TABLE
        )
        if runner.web is not None:
            if await table_exists(runner.web, SOURCE_TABLE):
                web_count = await get_row_count(runner.web, SOURCE_TABLE)
                logger.info(f"  Source row count (alchemi-web): {web_count:,}")

                web_query = _build_web_source_query()

                inserted = await _migrate_source(
                    source=runner.web,
                    dest=runner.dest,
                    source_query=web_query,
                    insert_from_staging_sql=insert_from_staging,
                    label="alchemi-web",
                )
                grand_total += inserted
            else:
                logger.warning(
                    "Source table %s not found in alchemi-web", SOURCE_TABLE
                )
        else:
            logger.warning("Skipping alchemi-web: connection unavailable")

        # ------------------------------------------------------------------
        # Cleanup
        # ------------------------------------------------------------------
        await runner.dest.execute(DROP_DEDUP_INDEX_SQL)
        await runner.dest.execute(DROP_STAGING_SQL)

        dest_final = await get_row_count(runner.dest, DEST_TABLE)
        logger.info(
            f"  {DEST_TABLE}: {grand_total:,} rows inserted this run, "
            f"{dest_final:,} total rows in destination"
        )


if __name__ == "__main__":
    setup_logging()
    asyncio.run(migrate_cost_tracking())
