#!/usr/bin/env python3
"""
Seed Copilot model catalog from provider model-list env vars.

Reads from .env (or process env) keys:
  - AZURE_OPENAI_MODELS
  - AZURE_ANTHROPIC_MODELS
  - AZURE_XAI_MODELS
  - VERTEX_AI_MODELS

Each list entry format:
  model_name:Display Label:profile[:json_overrides]

This script upserts copilot model catalog rows via API:
  GET    /copilot/models/catalog?include_inactive=true
  POST   /copilot/models/catalog
  PUT    /copilot/models/catalog/{id}
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

import httpx
from dotenv import dotenv_values


ENV_MODEL_SOURCES: List[Tuple[str, str]] = [
    ("AZURE_OPENAI_MODELS", "azure_openai"),
    ("AZURE_ANTHROPIC_MODELS", "azure_anthropic"),
    ("AZURE_XAI_MODELS", "azure_xai"),
    ("VERTEX_AI_MODELS", "vertex_ai"),
]


@dataclass
class Variant:
    label: str
    profile: str
    overrides: Dict[str, Any] = field(default_factory=dict)
    source_key: str = ""


@dataclass
class ModelAggregate:
    model_name: str
    provider: str
    display_name: str
    variants: List[Variant] = field(default_factory=list)


def _load_config() -> Dict[str, str]:
    env_path = os.path.join(os.getcwd(), ".env")
    file_env = dotenv_values(env_path) if os.path.exists(env_path) else {}
    merged: Dict[str, str] = {}
    for k, v in file_env.items():
        if isinstance(v, str):
            merged[k] = v
    for k, v in os.environ.items():
        merged[k] = v
    return merged


def _parse_model_entry(raw: str) -> Tuple[str, str, str, Dict[str, Any]]:
    parts = raw.split(":", 3)
    model_name = parts[0].strip() if len(parts) > 0 else ""
    display_name = parts[1].strip() if len(parts) > 1 else model_name
    profile = parts[2].strip() if len(parts) > 2 else "default"
    overrides_raw = parts[3].strip() if len(parts) > 3 else ""
    overrides: Dict[str, Any] = {}
    if overrides_raw:
        try:
            parsed = json.loads(overrides_raw)
            if isinstance(parsed, dict):
                overrides = parsed
        except Exception:
            overrides = {"raw": overrides_raw}
    return model_name, display_name, profile, overrides


def _parse_model_lists(cfg: Dict[str, str]) -> Dict[str, ModelAggregate]:
    aggregate: Dict[str, ModelAggregate] = {}
    for env_key, provider in ENV_MODEL_SOURCES:
        raw_list = str(cfg.get(env_key, "") or "").strip()
        if not raw_list:
            continue
        entries = [e.strip() for e in raw_list.split("|") if e.strip()]
        for entry in entries:
            model_name, display_name, profile, overrides = _parse_model_entry(entry)
            if not model_name:
                continue
            key = model_name.lower()
            if key not in aggregate:
                aggregate[key] = ModelAggregate(
                    model_name=model_name,
                    provider=provider,
                    display_name=display_name or model_name,
                    variants=[],
                )
            item = aggregate[key]
            if not item.display_name:
                item.display_name = display_name or model_name
            item.variants.append(
                Variant(
                    label=display_name or model_name,
                    profile=profile or "default",
                    overrides=overrides,
                    source_key=env_key,
                )
            )
    return aggregate


def _build_payload(item: ModelAggregate) -> Dict[str, Any]:
    variant_payload = [
        {
            "label": v.label,
            "profile": v.profile,
            "overrides": v.overrides,
            "source_key": v.source_key,
        }
        for v in item.variants
    ]
    metadata = {
        "source": "env_model_lists",
        "variants": variant_payload,
    }
    return {
        "model_name": item.model_name,
        "display_name": item.display_name or item.model_name,
        "provider": item.provider,
        "upstream_model_name": item.model_name,
        "credits_per_1k_tokens": 0.0,
        "is_active": True,
        "metadata": metadata,
    }


def main() -> int:
    cfg = _load_config()
    base_url = str(cfg.get("COPILOT_API_BASE_URL", "http://127.0.0.1:4001")).rstrip("/")
    master_key = str(cfg.get("LITELLM_MASTER_KEY", "")).strip()
    if not master_key:
        print("Missing LITELLM_MASTER_KEY in env/.env", file=sys.stderr)
        return 1

    aggregate = _parse_model_lists(cfg)
    if not aggregate:
        print("No model list env vars found. Nothing to seed.")
        return 0

    headers = {"Authorization": f"Bearer {master_key}", "Content-Type": "application/json"}

    created = 0
    updated = 0

    with httpx.Client(base_url=base_url, timeout=45.0) as client:
        resp = client.get("/copilot/models/catalog", params={"include_inactive": "true"}, headers=headers)
        if resp.status_code != 200:
            print(f"Failed to read model catalog: {resp.status_code} {resp.text}", file=sys.stderr)
            return 1
        rows = resp.json().get("data", [])
        existing_by_name = {
            str(r.get("model_name", "")).strip().lower(): r
            for r in rows
            if str(r.get("model_name", "")).strip()
        }

        for key in sorted(aggregate.keys()):
            payload = _build_payload(aggregate[key])
            existing = existing_by_name.get(key)

            if existing and existing.get("id"):
                catalog_id = str(existing["id"])
                # Preserve existing non-zero credits when present.
                existing_credits = existing.get("credits_per_1k_tokens")
                if isinstance(existing_credits, (int, float)) and float(existing_credits) > 0:
                    payload["credits_per_1k_tokens"] = float(existing_credits)
                update_resp = client.put(f"/copilot/models/catalog/{catalog_id}", json=payload, headers=headers)
                if update_resp.status_code != 200:
                    print(
                        f"Failed to update {payload['model_name']}: {update_resp.status_code} {update_resp.text}",
                        file=sys.stderr,
                    )
                    return 1
                updated += 1
            else:
                create_resp = client.post("/copilot/models/catalog", json=payload, headers=headers)
                if create_resp.status_code != 200:
                    print(
                        f"Failed to create {payload['model_name']}: {create_resp.status_code} {create_resp.text}",
                        file=sys.stderr,
                    )
                    return 1
                created += 1

    total = len(aggregate)
    print(f"Seeded copilot model catalog from env lists. total={total} created={created} updated={updated}")
    print("Models:")
    for key in sorted(aggregate.keys()):
        item = aggregate[key]
        print(f"- {item.model_name} ({item.provider}) variants={len(item.variants)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
