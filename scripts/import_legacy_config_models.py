#!/usr/bin/env python3
"""Import legacy config_models/config_providers into LiteLLM_ProxyModelTable.

Usage:
  python scripts/import_legacy_config_models.py \
    --source-url "$LEGACY_DB_URL" \
    --target-url "$DATABASE_URL"
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

import psycopg
from psycopg.rows import dict_row


@dataclass(frozen=True)
class ProviderDefaults:
    litellm_provider: str
    api_base_env_var: Optional[str]
    api_key_env_var: Optional[str]


PROVIDER_DEFAULTS: Dict[str, ProviderDefaults] = {
    "azure_openai": ProviderDefaults(
        litellm_provider="azure",
        api_base_env_var="AZURE_OPENAI_ENDPOINT",
        api_key_env_var="AZURE_OPENAI_API_KEY",
    ),
    "azure_anthropic": ProviderDefaults(
        litellm_provider="anthropic",
        api_base_env_var="AZURE_ANTHROPIC_ENDPOINT",
        api_key_env_var="AZURE_ANTHROPIC_API_KEY",
    ),
    "azure_xai": ProviderDefaults(
        litellm_provider="openai",
        api_base_env_var="AZURE_XAI_ENDPOINT",
        api_key_env_var="AZURE_XAI_API_KEY",
    ),
    "vertex_ai": ProviderDefaults(
        litellm_provider="gemini",
        api_base_env_var=None,
        api_key_env_var="GOOGLE_API_KEY",
    ),
}


def env_ref(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return f"os.environ/{name}"


def build_payload(row: Dict[str, Any], model_id: str) -> Dict[str, Any]:
    provider_id = str(row.get("provider_id") or "").strip().lower()
    defaults = PROVIDER_DEFAULTS.get(provider_id)
    deployment_name = str(row.get("deployment_name") or "").strip()
    if not deployment_name:
        raise ValueError(f"Missing deployment_name for model alias={row.get('model_alias')}")

    litellm_model = deployment_name
    if defaults and defaults.litellm_provider:
        litellm_model = f"{defaults.litellm_provider}/{deployment_name}"

    litellm_params: Dict[str, Any] = {"model": litellm_model}
    if defaults:
        base_ref = env_ref(defaults.api_base_env_var)
        key_ref = env_ref(defaults.api_key_env_var)
        if base_ref:
            litellm_params["api_base"] = base_ref
        if key_ref:
            litellm_params["api_key"] = key_ref
    if row.get("extra_body"):
        litellm_params["extra_body"] = row["extra_body"]

    input_cost_per_million = row.get("input_cost_per_million")
    output_cost_per_million = row.get("output_cost_per_million")

    model_info: Dict[str, Any] = {
        "id": model_id,
        "display_name": row.get("display_name") or row.get("model_alias"),
        "provider_id": provider_id,
        "provider_label": row.get("provider_label"),
        "deployment_name": deployment_name,
        "capability": row.get("capability"),
        "is_active": bool(row.get("is_active", True)),
        "sort_order": int(row.get("sort_order") or 100),
        "source": "legacy_config_models",
        "api_base_env_var": defaults.api_base_env_var if defaults else None,
        "api_key_env_var": defaults.api_key_env_var if defaults else None,
        "input_cost_per_token": (float(input_cost_per_million) / 1_000_000.0) if input_cost_per_million is not None else None,
        "output_cost_per_token": (float(output_cost_per_million) / 1_000_000.0) if output_cost_per_million is not None else None,
        "content_capabilities": row.get("content_capabilities") or {},
    }
    if row.get("extra_body"):
        model_info["extra_body"] = row["extra_body"]

    model_info = {k: v for k, v in model_info.items() if v is not None}

    return {"litellm_params": litellm_params, "model_info": model_info}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import legacy model config into LiteLLM_ProxyModelTable")
    parser.add_argument("--source-url", default=os.getenv("LEGACY_MODEL_SOURCE_DATABASE_URL"))
    parser.add_argument("--target-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.source_url:
        raise SystemExit("Missing --source-url (or LEGACY_MODEL_SOURCE_DATABASE_URL)")
    if not args.target_url:
        raise SystemExit("Missing --target-url (or DATABASE_URL)")

    with psycopg.connect(args.source_url, row_factory=dict_row) as source_conn, psycopg.connect(
        args.target_url, row_factory=dict_row
    ) as target_conn:
        source_rows = source_conn.execute(
            """
            SELECT
              m.id AS model_alias,
              m.provider_id,
              m.deployment_name,
              m.display_name,
              m.capability,
              m.input_cost_per_million,
              m.output_cost_per_million,
              m.content_capabilities,
              m.extra_body,
              m.is_active,
              m.sort_order,
              p.display_label AS provider_label
            FROM public.config_models m
            LEFT JOIN public.config_providers p ON p.id = m.provider_id
            ORDER BY COALESCE(m.sort_order, 100), m.id
            """
        ).fetchall()

        existing_rows = target_conn.execute(
            """
            SELECT model_id, model_name
            FROM "LiteLLM_ProxyModelTable"
            WHERE account_id IS NULL
            """
        ).fetchall()
        existing_by_name = {str(row["model_name"]): str(row["model_id"]) for row in existing_rows}

        inserted = 0
        updated = 0
        for row in source_rows:
            model_name = str(row["model_alias"])
            existing_model_id = existing_by_name.get(model_name)
            model_id = existing_model_id or str(uuid.uuid4())
            payload = build_payload(row, model_id=model_id)

            if args.dry_run:
                continue

            if existing_model_id:
                target_conn.execute(
                    """
                    UPDATE "LiteLLM_ProxyModelTable"
                    SET
                      litellm_params = %s::jsonb,
                      model_info = %s::jsonb,
                      updated_by = %s,
                      updated_at = CURRENT_TIMESTAMP
                    WHERE model_id = %s
                    """,
                    (
                        json.dumps(payload["litellm_params"]),
                        json.dumps(payload["model_info"]),
                        "legacy_import",
                        model_id,
                    ),
                )
                updated += 1
            else:
                target_conn.execute(
                    """
                    INSERT INTO "LiteLLM_ProxyModelTable"
                      (model_id, model_name, litellm_params, model_info, created_by, updated_by, account_id, created_at, updated_at)
                    VALUES
                      (%s, %s, %s::jsonb, %s::jsonb, %s, %s, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        model_id,
                        model_name,
                        json.dumps(payload["litellm_params"]),
                        json.dumps(payload["model_info"]),
                        "legacy_import",
                        "legacy_import",
                    ),
                )
                inserted += 1

        if args.dry_run:
            print(f"[dry-run] source models={len(source_rows)} existing_target_models={len(existing_rows)}")
            return 0

        target_conn.commit()
        print(f"Imported legacy models: inserted={inserted} updated={updated} total_source={len(source_rows)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
