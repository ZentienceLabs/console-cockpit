"""
Migrate financial data from alchemi-web and alchemi-ai into console-cockpit.

Tables:
  1. budget_plans       (alchemi-web)  -> Alchemi_BudgetPlanTable
  2. credit_budget      (both DBs)     -> Alchemi_CreditBudgetTable  (dedup by scope_type, scope_id, cycle_start; web canonical)
  3. account_quotas     (alchemi-ai)   -> Alchemi_AccountQuotaTable  (dedup by account_id, unit, period_start; ai canonical)

Idempotent: uses ON CONFLICT DO NOTHING so it is safe to re-run.
"""

import asyncio
import sys

sys.path.insert(0, "/workspaces/console-cockpit/scripts/migrate")
from common import MigrationRunner, migrate_table, migrate_with_dedup, setup_logging, logger, table_exists


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

BUDGET_PLAN_COLUMNS = [
    "id",
    "account_id",
    "name",
    "is_active",
    "distribution",
    "created_at",
    "updated_at",
]

CREDIT_BUDGET_COLUMNS = [
    "id",
    "account_id",
    "budget_plan_id",
    "scope_type",
    "scope_id",
    "allocated",
    "limit_amount",
    "overflow_cap",
    "used",
    "overflow_used",
    "cycle_start",
    "cycle_end",
    "created_at",
    "updated_at",
]

ACCOUNT_QUOTA_COLUMNS = [
    "id",
    "account_id",
    "subscription_id",
    "product_code",
    "feature_code",
    "unit",
    "included",
    "used",
    "overage_used",
    "overage_limit",
    "reset_policy",
    "rollover_enabled",
    "rollover_cap",
    "rollover_from_previous",
    "period_start",
    "period_end",
    "is_active",
    "created_at",
    "updated_at",
]

# Minimal set of columns that alchemi-web's account_quotas might have
# (it may lack the rollover-related fields).  The source query pads
# missing columns with NULL defaults so the row shape always matches
# ACCOUNT_QUOTA_COLUMNS.
ACCOUNT_QUOTA_WEB_FALLBACK_QUERY = """
SELECT
    id,
    account_id,
    subscription_id,
    product_code,
    feature_code,
    unit,
    included,
    used,
    overage_used,
    overage_limit,
    reset_policy,
    COALESCE(rollover_enabled, false)       AS rollover_enabled,
    COALESCE(rollover_cap, 0)               AS rollover_cap,
    COALESCE(rollover_from_previous, 0)     AS rollover_from_previous,
    period_start,
    period_end,
    is_active,
    created_at,
    updated_at
FROM account_quotas
ORDER BY id
""".strip()


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------

async def migrate_budget_plans(runner: MigrationRunner) -> None:
    """Migrate budget_plans from alchemi-web only."""
    logger.info("--- Step 1: budget_plans -> Alchemi_BudgetPlanTable ---")

    if runner.web is None:
        logger.warning("Skipping budget_plans: alchemi-web connection unavailable")
        return

    try:
        if not await table_exists(runner.web, "budget_plans"):
            logger.warning("Skipping budget_plans: source table does not exist in alchemi-web")
            return

        await migrate_table(
            source=runner.web,
            dest=runner.dest,
            source_table="budget_plans",
            dest_table="Alchemi_BudgetPlanTable",
            columns=BUDGET_PLAN_COLUMNS,
            conflict_columns=["id"],
        )
    except Exception as exc:
        logger.error(f"Failed to migrate budget_plans: {exc}")


async def migrate_credit_budget(runner: MigrationRunner) -> None:
    """Migrate credit_budget from both DBs with dedup; alchemi-web is canonical."""
    logger.info("--- Step 2: credit_budget -> Alchemi_CreditBudgetTable ---")

    sources = []
    col_str = ", ".join(f'"{c}"' for c in CREDIT_BUDGET_COLUMNS)

    # Canonical source first: alchemi-web
    if runner.web is not None:
        try:
            if await table_exists(runner.web, "credit_budget"):
                query = f'SELECT {col_str} FROM "credit_budget" ORDER BY "id"'
                sources.append((runner.web, query, "alchemi-web"))
            else:
                logger.warning("credit_budget table not found in alchemi-web")
        except Exception as exc:
            logger.warning(f"Error checking credit_budget in alchemi-web: {exc}")
    else:
        logger.warning("Skipping alchemi-web source for credit_budget: connection unavailable")

    # Secondary source: alchemi-ai
    if runner.ai is not None:
        try:
            if await table_exists(runner.ai, "credit_budget"):
                query = f'SELECT {col_str} FROM "credit_budget" ORDER BY "id"'
                sources.append((runner.ai, query, "alchemi-ai"))
            else:
                logger.info("credit_budget table not found in alchemi-ai (ok, web is canonical)")
        except Exception as exc:
            logger.warning(f"Error checking credit_budget in alchemi-ai: {exc}")
    else:
        logger.info("alchemi-ai connection unavailable for credit_budget (non-critical)")

    if not sources:
        logger.warning("No sources available for credit_budget, skipping")
        return

    try:
        await migrate_with_dedup(
            sources=sources,
            dest=runner.dest,
            dest_table="Alchemi_CreditBudgetTable",
            columns=CREDIT_BUDGET_COLUMNS,
            dedup_key=["scope_type", "scope_id", "cycle_start"],
        )
    except Exception as exc:
        logger.error(f"Failed to migrate credit_budget: {exc}")


async def migrate_account_quotas(runner: MigrationRunner) -> None:
    """Migrate account_quotas from both DBs with dedup; alchemi-ai is canonical."""
    logger.info("--- Step 3: account_quotas -> Alchemi_AccountQuotaTable ---")

    sources = []
    col_str = ", ".join(f'"{c}"' for c in ACCOUNT_QUOTA_COLUMNS)

    # Canonical source first: alchemi-ai
    if runner.ai is not None:
        try:
            if await table_exists(runner.ai, "account_quotas"):
                query = f'SELECT {col_str} FROM "account_quotas" ORDER BY "id"'
                sources.append((runner.ai, query, "alchemi-ai"))
            else:
                logger.warning("account_quotas table not found in alchemi-ai")
        except Exception as exc:
            logger.warning(f"Error checking account_quotas in alchemi-ai: {exc}")
    else:
        logger.warning("Skipping alchemi-ai source for account_quotas: connection unavailable")

    # Secondary source: alchemi-web (may have fewer rollover columns)
    if runner.web is not None:
        try:
            if await table_exists(runner.web, "account_quotas"):
                sources.append((runner.web, ACCOUNT_QUOTA_WEB_FALLBACK_QUERY, "alchemi-web"))
            else:
                logger.info("account_quotas table not found in alchemi-web (ok, ai is canonical)")
        except Exception as exc:
            logger.warning(f"Error checking account_quotas in alchemi-web: {exc}")
    else:
        logger.info("alchemi-web connection unavailable for account_quotas (non-critical)")

    if not sources:
        logger.warning("No sources available for account_quotas, skipping")
        return

    try:
        await migrate_with_dedup(
            sources=sources,
            dest=runner.dest,
            dest_table="Alchemi_AccountQuotaTable",
            columns=ACCOUNT_QUOTA_COLUMNS,
            dedup_key=["account_id", "unit", "period_start"],
        )
    except Exception as exc:
        logger.error(f"Failed to migrate account_quotas: {exc}")


async def migrate_financial() -> None:
    """Run all financial data migrations."""
    async with MigrationRunner("financial", needs_web=True, needs_ai=True) as runner:
        await migrate_budget_plans(runner)
        await migrate_credit_budget(runner)
        await migrate_account_quotas(runner)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(migrate_financial())
