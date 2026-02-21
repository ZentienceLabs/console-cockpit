"""
Migrate configuration data from alchemi-ai into console-cockpit.

Tables:
  1. config_providers       -> Alchemi_ConfigProviderTable
  2. config_models          -> Alchemi_ConfigModelTable
  3. config_default_models  -> Alchemi_ConfigDefaultModelTable
  4. config_sandbox_pricing -> Alchemi_ConfigSandboxPricingTable

All four tables exist only in alchemi-ai (single source, no dedup needed).

Migration order respects foreign keys:
  - config_providers first (referenced by config_models.provider_id)
  - config_models second (referenced by config_default_models.model_id)
  - config_default_models and config_sandbox_pricing last

Idempotent: uses ON CONFLICT DO NOTHING so it is safe to re-run.
"""

import asyncio
import json
import sys
from decimal import Decimal

sys.path.insert(0, "/workspaces/console-cockpit/scripts/migrate")
from common import MigrationRunner, migrate_table, table_exists, setup_logging, logger


# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

CONFIG_PROVIDER_COLUMNS = [
    "id",
    "name",
    "display_label",
    "endpoint_env_var",
    "api_key_env_var",
    "is_active",
    "account_id",
    "created_at",
    "updated_at",
]

CONFIG_MODEL_COLUMNS = [
    "id",
    "provider_id",
    "deployment_name",
    "display_name",
    "capability",
    "input_cost_per_million",
    "output_cost_per_million",
    "content_capabilities",
    "extra_body",
    "sort_order",
    "is_active",
    "account_id",
    "created_at",
    "updated_at",
]

CONFIG_DEFAULT_MODEL_COLUMNS = [
    "id",
    "model_id",
    "account_id",
    "created_at",
    "updated_at",
]

CONFIG_SANDBOX_PRICING_COLUMNS = [
    "id",
    "resource_type",
    "unit",
    "cost_usd",
    "description",
    "effective_from",
    "effective_to",
    "account_id",
    "created_at",
    "updated_at",
]


# ---------------------------------------------------------------------------
# Row transforms
# ---------------------------------------------------------------------------

def _transform_model_row(row: dict) -> tuple:
    """
    Transform a config_models row, ensuring JSONB fields are serialised as
    JSON strings (for text/jsonb destination columns) and cost columns are
    proper Decimal values.
    """
    content_caps = row.get("content_capabilities")
    if content_caps is not None and not isinstance(content_caps, str):
        content_caps = json.dumps(content_caps)

    extra_body = row.get("extra_body")
    if extra_body is not None and not isinstance(extra_body, str):
        extra_body = json.dumps(extra_body)

    input_cost = row.get("input_cost_per_million")
    if input_cost is not None and not isinstance(input_cost, Decimal):
        input_cost = Decimal(str(input_cost))

    output_cost = row.get("output_cost_per_million")
    if output_cost is not None and not isinstance(output_cost, Decimal):
        output_cost = Decimal(str(output_cost))

    return (
        row["id"],
        row["provider_id"],
        row["deployment_name"],
        row["display_name"],
        row["capability"],
        input_cost,
        output_cost,
        content_caps,
        extra_body,
        row["sort_order"],
        row["is_active"],
        row["account_id"],
        row["created_at"],
        row["updated_at"],
    )


# ---------------------------------------------------------------------------
# Per-table migration helpers
# ---------------------------------------------------------------------------

async def migrate_config_providers(runner: MigrationRunner) -> None:
    """Migrate config_providers from alchemi-ai."""
    logger.info("--- Step 1: config_providers -> Alchemi_ConfigProviderTable ---")

    if not await table_exists(runner.ai, "config_providers"):
        logger.warning("Skipping config_providers: source table does not exist in alchemi-ai")
        return

    await migrate_table(
        source=runner.ai,
        dest=runner.dest,
        source_table="config_providers",
        dest_table="Alchemi_ConfigProviderTable",
        columns=CONFIG_PROVIDER_COLUMNS,
        conflict_columns=["id"],
    )


async def migrate_config_models(runner: MigrationRunner) -> None:
    """Migrate config_models from alchemi-ai."""
    logger.info("--- Step 2: config_models -> Alchemi_ConfigModelTable ---")

    if not await table_exists(runner.ai, "config_models"):
        logger.warning("Skipping config_models: source table does not exist in alchemi-ai")
        return

    await migrate_table(
        source=runner.ai,
        dest=runner.dest,
        source_table="config_models",
        dest_table="Alchemi_ConfigModelTable",
        columns=CONFIG_MODEL_COLUMNS,
        transform_row=_transform_model_row,
        conflict_columns=["id"],
    )


async def migrate_config_default_models(runner: MigrationRunner) -> None:
    """Migrate config_default_models from alchemi-ai."""
    logger.info("--- Step 3: config_default_models -> Alchemi_ConfigDefaultModelTable ---")

    if not await table_exists(runner.ai, "config_default_models"):
        logger.warning("Skipping config_default_models: source table does not exist in alchemi-ai")
        return

    await migrate_table(
        source=runner.ai,
        dest=runner.dest,
        source_table="config_default_models",
        dest_table="Alchemi_ConfigDefaultModelTable",
        columns=CONFIG_DEFAULT_MODEL_COLUMNS,
        conflict_columns=["id"],
    )


async def migrate_config_sandbox_pricing(runner: MigrationRunner) -> None:
    """Migrate config_sandbox_pricing from alchemi-ai."""
    logger.info("--- Step 4: config_sandbox_pricing -> Alchemi_ConfigSandboxPricingTable ---")

    if not await table_exists(runner.ai, "config_sandbox_pricing"):
        logger.warning("Skipping config_sandbox_pricing: source table does not exist in alchemi-ai")
        return

    await migrate_table(
        source=runner.ai,
        dest=runner.dest,
        source_table="config_sandbox_pricing",
        dest_table="Alchemi_ConfigSandboxPricingTable",
        columns=CONFIG_SANDBOX_PRICING_COLUMNS,
        conflict_columns=["id"],
    )


# ---------------------------------------------------------------------------
# Main migration
# ---------------------------------------------------------------------------

async def migrate_config():
    """Run all configuration data migrations."""
    async with MigrationRunner("config", needs_web=False, needs_ai=True) as runner:
        if not runner.ai:
            logger.error("Cannot connect to alchemi-ai database")
            return

        # Respect FK ordering: providers -> models -> default_models, sandbox_pricing
        await migrate_config_providers(runner)
        await migrate_config_models(runner)
        await migrate_config_default_models(runner)
        await migrate_config_sandbox_pricing(runner)


if __name__ == "__main__":
    setup_logging()
    asyncio.run(migrate_config())
