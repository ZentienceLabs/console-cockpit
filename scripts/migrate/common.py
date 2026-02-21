"""
Common utilities for data migration scripts.

Usage:
    Set these environment variables before running:
    - ALCHEMI_WEB_DB_URL: Connection string for alchemi-web's PostgreSQL (source)
    - ALCHEMI_AI_DB_URL: Connection string for alchemi-ai's APP_POSTGRES_URI (source)
    - CONSOLE_DB_URL: Connection string for console-cockpit's PostgreSQL (destination)

All scripts are idempotent (safe to re-run) using ON CONFLICT DO NOTHING.
"""

import asyncio
import asyncpg
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("migrate")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure logging for migration scripts."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)


def get_web_db_url() -> str:
    """Get alchemi-web source database URL."""
    url = os.environ.get("ALCHEMI_WEB_DB_URL", "")
    if not url:
        raise EnvironmentError("ALCHEMI_WEB_DB_URL is required")
    return url


def get_ai_db_url() -> str:
    """Get alchemi-ai source database URL."""
    url = os.environ.get("ALCHEMI_AI_DB_URL", "")
    if not url:
        raise EnvironmentError("ALCHEMI_AI_DB_URL is required")
    return url


def get_dest_db_url() -> str:
    """Get console-cockpit destination database URL."""
    url = os.environ.get("CONSOLE_DB_URL", "")
    if not url:
        raise EnvironmentError("CONSOLE_DB_URL is required")
    return url


async def connect_source_web() -> asyncpg.Connection:
    """Connect to alchemi-web source database."""
    return await asyncpg.connect(get_web_db_url())


async def connect_source_ai() -> asyncpg.Connection:
    """Connect to alchemi-ai source database."""
    return await asyncpg.connect(get_ai_db_url())


async def connect_dest() -> asyncpg.Connection:
    """Connect to console-cockpit destination database."""
    return await asyncpg.connect(get_dest_db_url())


async def table_exists(conn: asyncpg.Connection, table_name: str) -> bool:
    """Check if a table exists in the connected database."""
    result = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = $1
        )
        """,
        table_name,
    )
    return bool(result)


async def get_row_count(conn: asyncpg.Connection, table_name: str) -> int:
    """Get approximate row count for a table."""
    try:
        result = await conn.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')
        return int(result or 0)
    except Exception:
        return 0


BATCH_SIZE = 1000


async def migrate_table(
    source: asyncpg.Connection,
    dest: asyncpg.Connection,
    source_table: str,
    dest_table: str,
    columns: List[str],
    source_columns: Optional[List[str]] = None,
    transform_row: Optional[Any] = None,
    conflict_columns: Optional[List[str]] = None,
    source_query: Optional[str] = None,
    batch_size: int = BATCH_SIZE,
) -> int:
    """
    Migrate data from source table to destination table in batches.

    Args:
        source: Source database connection
        dest: Destination database connection
        source_table: Source table name (unquoted for simple tables)
        dest_table: Destination table name (will be quoted for case-sensitive Prisma names)
        columns: Column names in the destination table
        source_columns: Column names in the source table (if different from dest columns)
        transform_row: Optional function to transform a source row dict to dest values tuple
        conflict_columns: Columns for ON CONFLICT (if None, uses DO NOTHING with no specific target)
        source_query: Optional custom SELECT query (overrides source_table)
        batch_size: Number of rows per batch

    Returns:
        Total number of rows processed
    """
    src_cols = source_columns or columns
    if source_query is None:
        src_col_str = ", ".join(f'"{c}"' for c in src_cols)
        source_query = f'SELECT {src_col_str} FROM "{source_table}" ORDER BY 1'

    # Build INSERT statement
    dest_col_str = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))

    if conflict_columns:
        conflict_str = ", ".join(f'"{c}"' for c in conflict_columns)
        insert_sql = (
            f'INSERT INTO "{dest_table}" ({dest_col_str}) '
            f"VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict_str}) DO NOTHING"
        )
    else:
        insert_sql = (
            f'INSERT INTO "{dest_table}" ({dest_col_str}) '
            f"VALUES ({placeholders}) "
            f"ON CONFLICT DO NOTHING"
        )

    total = 0
    offset = 0
    start_time = time.time()

    while True:
        batch_query = f"{source_query} LIMIT {batch_size} OFFSET {offset}"
        rows = await source.fetch(batch_query)

        if not rows:
            break

        # Transform rows
        if transform_row:
            values = [transform_row(dict(r)) for r in rows]
        else:
            values = [tuple(r[c] for c in src_cols) for r in rows]

        # Insert batch
        try:
            await dest.executemany(insert_sql, values)
            total += len(rows)
        except Exception as e:
            logger.error(
                f"Error inserting batch at offset {offset} into {dest_table}: {e}"
            )
            # Try row-by-row for this batch to skip problematic rows
            for i, val in enumerate(values):
                try:
                    await dest.execute(insert_sql, *val)
                    total += 1
                except Exception as row_err:
                    logger.warning(
                        f"  Skipping row {offset + i}: {row_err}"
                    )

        offset += batch_size
        if len(rows) < batch_size:
            break

    elapsed = time.time() - start_time
    logger.info(
        f"  {dest_table}: migrated {total} rows in {elapsed:.1f}s"
    )
    return total


async def migrate_with_dedup(
    sources: List[Tuple[asyncpg.Connection, str, Optional[str]]],
    dest: asyncpg.Connection,
    dest_table: str,
    columns: List[str],
    dedup_key: List[str],
    transform_row: Optional[Any] = None,
    batch_size: int = BATCH_SIZE,
) -> int:
    """
    Migrate from multiple sources with deduplication.
    First source is canonical (wins on conflict).

    Args:
        sources: List of (connection, source_query, label) tuples.
                 First source is canonical.
        dest: Destination connection
        dest_table: Destination table name
        columns: Destination column names
        dedup_key: Columns used for dedup (ON CONFLICT target)
        transform_row: Optional row transformer
        batch_size: Batch size

    Returns:
        Total rows processed
    """
    total = 0
    conflict_str = ", ".join(f'"{c}"' for c in dedup_key)
    dest_col_str = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))

    insert_sql = (
        f'INSERT INTO "{dest_table}" ({dest_col_str}) '
        f"VALUES ({placeholders}) "
        f"ON CONFLICT ({conflict_str}) DO NOTHING"
    )

    for source_conn, source_query, label in sources:
        source_label = label or "unknown"
        logger.info(f"  Source: {source_label}")
        offset = 0
        source_total = 0

        while True:
            batch_query = f"{source_query} LIMIT {batch_size} OFFSET {offset}"
            try:
                rows = await source_conn.fetch(batch_query)
            except Exception as e:
                logger.warning(f"  Source {source_label} query failed: {e}")
                break

            if not rows:
                break

            if transform_row:
                values = [transform_row(dict(r)) for r in rows]
            else:
                values = [tuple(dict(r).values()) for r in rows]

            try:
                await dest.executemany(insert_sql, values)
                source_total += len(rows)
            except Exception as e:
                logger.error(f"  Batch insert error from {source_label}: {e}")
                for val in values:
                    try:
                        await dest.execute(insert_sql, *val)
                        source_total += 1
                    except Exception:
                        pass

            offset += batch_size
            if len(rows) < batch_size:
                break

        logger.info(f"    {source_label}: {source_total} rows")
        total += source_total

    logger.info(f"  {dest_table}: total {total} rows from {len(sources)} sources")
    return total


class MigrationRunner:
    """Context manager for running a migration script."""

    def __init__(self, name: str, needs_web: bool = True, needs_ai: bool = False):
        self.name = name
        self.needs_web = needs_web
        self.needs_ai = needs_ai
        self.web: Optional[asyncpg.Connection] = None
        self.ai: Optional[asyncpg.Connection] = None
        self.dest: Optional[asyncpg.Connection] = None

    async def __aenter__(self):
        logger.info(f"=== Starting migration: {self.name} ===")
        self.dest = await connect_dest()
        if self.needs_web:
            try:
                self.web = await connect_source_web()
            except Exception as e:
                logger.warning(f"Could not connect to alchemi-web DB: {e}")
        if self.needs_ai:
            try:
                self.ai = await connect_source_ai()
            except Exception as e:
                logger.warning(f"Could not connect to alchemi-ai DB: {e}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for conn in [self.web, self.ai, self.dest]:
            if conn:
                try:
                    await conn.close()
                except Exception:
                    pass
        if exc_type:
            logger.error(f"=== Migration {self.name} FAILED: {exc_val} ===")
        else:
            logger.info(f"=== Migration {self.name} complete ===")
        return False
