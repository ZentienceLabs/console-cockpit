#!/usr/bin/env python3
"""
Master migration orchestrator.

Runs all data migration scripts in the correct order (respecting FK dependencies).

Usage:
    export ALCHEMI_WEB_DB_URL="postgresql://user:pass@host:5432/devapp_db"
    export ALCHEMI_AI_DB_URL="postgresql://user:pass@host:5432/aiapp_db"
    export CONSOLE_DB_URL="postgresql://user:pass@host:5432/console_db"

    python run_all.py [--dry-run] [--only SCRIPT_NAME] [--skip SCRIPT_NAME]

All scripts are idempotent and safe to re-run.
"""

import argparse
import asyncio
import importlib
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import setup_logging, get_web_db_url, get_ai_db_url, get_dest_db_url

logger = logging.getLogger("migrate.runner")

# Migration scripts in dependency order.
# Each entry: (module_name, async_function_name, description, requires_web, requires_ai)
MIGRATION_ORDER = [
    # Phase 1: Platform-wide tables (no FK deps)
    ("migrate_single_source", "migrate_all_single_source", "Single-source tables from alchemi-web", True, False),

    # Phase 2: Config tables from alchemi-ai (no FK deps to web tables)
    ("migrate_config", "migrate_config", "Config tables from alchemi-ai", False, True),

    # Phase 3: Tables with dual-source deduplication
    ("migrate_agents", "migrate_agents", "Agent registry (dedup: web canonical)", True, True),
    ("migrate_financial", "migrate_financial", "Financial tables (dedup: mixed canonical)", True, True),
    ("migrate_cost_tracking", "migrate_cost_tracking", "Cost tracking (dedup: ai canonical)", True, True),
]


async def run_migration(module_name: str, func_name: str, description: str) -> bool:
    """Run a single migration script. Returns True on success."""
    logger.info(f"")
    logger.info(f"{'=' * 60}")
    logger.info(f"Running: {description}")
    logger.info(f"  Module: {module_name}.{func_name}")
    logger.info(f"{'=' * 60}")

    start = time.time()
    try:
        mod = importlib.import_module(module_name)
        func = getattr(mod, func_name)
        await func()
        elapsed = time.time() - start
        logger.info(f"  Completed in {elapsed:.1f}s")
        return True
    except Exception as e:
        elapsed = time.time() - start
        logger.error(f"  FAILED after {elapsed:.1f}s: {e}", exc_info=True)
        return False


async def main(args: argparse.Namespace) -> int:
    """Run all migrations in order."""
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    logger.info("=" * 60)
    logger.info("Alchemi Data Migration")
    logger.info("=" * 60)

    # Validate environment
    errors = []
    try:
        web_url = get_web_db_url()
        logger.info(f"  Web DB: {web_url[:40]}...")
    except EnvironmentError:
        if not args.skip_web:
            errors.append("ALCHEMI_WEB_DB_URL not set (use --skip-web to skip web-dependent migrations)")

    try:
        ai_url = get_ai_db_url()
        logger.info(f"  AI DB:  {ai_url[:40]}...")
    except EnvironmentError:
        if not args.skip_ai:
            errors.append("ALCHEMI_AI_DB_URL not set (use --skip-ai to skip ai-dependent migrations)")

    try:
        dest_url = get_dest_db_url()
        logger.info(f"  Dest:   {dest_url[:40]}...")
    except EnvironmentError:
        errors.append("CONSOLE_DB_URL not set (required)")

    if errors:
        for err in errors:
            logger.error(f"  ERROR: {err}")
        return 1

    if args.dry_run:
        logger.info("")
        logger.info("DRY RUN - would execute:")
        for module_name, func_name, description, needs_web, needs_ai in MIGRATION_ORDER:
            skip = False
            if args.only and module_name not in args.only:
                skip = True
            if args.skip and module_name in args.skip:
                skip = True
            if args.skip_web and needs_web:
                skip = True
            if args.skip_ai and needs_ai:
                skip = True
            status = "SKIP" if skip else "RUN"
            logger.info(f"  [{status}] {module_name}: {description}")
        return 0

    # Run migrations
    total_start = time.time()
    results = {}

    for module_name, func_name, description, needs_web, needs_ai in MIGRATION_ORDER:
        if args.only and module_name not in args.only:
            logger.info(f"Skipping {module_name} (not in --only list)")
            continue
        if args.skip and module_name in args.skip:
            logger.info(f"Skipping {module_name} (in --skip list)")
            continue
        if args.skip_web and needs_web:
            logger.info(f"Skipping {module_name} (requires web DB, --skip-web set)")
            continue
        if args.skip_ai and needs_ai:
            logger.info(f"Skipping {module_name} (requires ai DB, --skip-ai set)")
            continue

        success = await run_migration(module_name, func_name, description)
        results[module_name] = success

        if not success and not args.continue_on_error:
            logger.error(f"Migration failed. Use --continue-on-error to skip failures.")
            break

    total_elapsed = time.time() - total_start

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("Migration Summary")
    logger.info("=" * 60)
    for name, success in results.items():
        status = "OK" if success else "FAILED"
        logger.info(f"  [{status}] {name}")
    logger.info(f"  Total time: {total_elapsed:.1f}s")

    failed = sum(1 for s in results.values() if not s)
    if failed:
        logger.error(f"  {failed} migration(s) failed")
        return 1

    logger.info("  All migrations completed successfully")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Alchemi data migrations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be run without executing")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    parser.add_argument("--only", nargs="+", help="Only run these migration modules")
    parser.add_argument("--skip", nargs="+", help="Skip these migration modules")
    parser.add_argument("--skip-web", action="store_true", help="Skip migrations requiring alchemi-web DB")
    parser.add_argument("--skip-ai", action="store_true", help="Skip migrations requiring alchemi-ai DB")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue even if a migration fails")

    args = parser.parse_args()
    exit_code = asyncio.run(main(args))
    sys.exit(exit_code)
