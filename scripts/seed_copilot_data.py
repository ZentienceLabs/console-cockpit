#!/usr/bin/env python3
"""
Seed script for Copilot data.

Seeds model catalog, feature catalog, and sample marketplace listings
via the copilot API endpoints.

Usage:
    python scripts/seed_copilot_data.py

Environment:
    LITELLM_PROXY_URL   Base URL (default: http://localhost:4000)
    LITELLM_API_KEY     Super admin API key (required)
"""

import os
import sys
import json
import httpx

BASE_URL = os.environ.get("LITELLM_PROXY_URL", "http://localhost:4000")
API_KEY = os.environ.get("LITELLM_API_KEY", "")

if not API_KEY:
    print("ERROR: Set LITELLM_API_KEY environment variable to a super admin key.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

client = httpx.Client(base_url=BASE_URL, headers=HEADERS, timeout=30)


def seed_model_catalog():
    """Seed model catalog with common models."""
    models = [
        {"model_code": "gpt-4o", "display_name": "GPT-4o", "provider": "openai", "category": "chat", "status": "active"},
        {"model_code": "gpt-4o-mini", "display_name": "GPT-4o Mini", "provider": "openai", "category": "chat", "status": "active"},
        {"model_code": "gpt-4-turbo", "display_name": "GPT-4 Turbo", "provider": "openai", "category": "chat", "status": "active"},
        {"model_code": "o1", "display_name": "o1", "provider": "openai", "category": "chat", "status": "active"},
        {"model_code": "o1-mini", "display_name": "o1 Mini", "provider": "openai", "category": "chat", "status": "active"},
        {"model_code": "claude-3.5-sonnet", "display_name": "Claude 3.5 Sonnet", "provider": "anthropic", "category": "chat", "status": "active"},
        {"model_code": "claude-3.5-haiku", "display_name": "Claude 3.5 Haiku", "provider": "anthropic", "category": "chat", "status": "active"},
        {"model_code": "claude-3-opus", "display_name": "Claude 3 Opus", "provider": "anthropic", "category": "chat", "status": "active"},
        {"model_code": "gemini-2.0-flash", "display_name": "Gemini 2.0 Flash", "provider": "google", "category": "chat", "status": "active"},
        {"model_code": "gemini-1.5-pro", "display_name": "Gemini 1.5 Pro", "provider": "google", "category": "chat", "status": "active"},
        {"model_code": "mistral-large", "display_name": "Mistral Large", "provider": "mistral", "category": "chat", "status": "active"},
        {"model_code": "grok-2", "display_name": "Grok 2", "provider": "xai", "category": "chat", "status": "active"},
        {"model_code": "text-embedding-3-large", "display_name": "Text Embedding 3 Large", "provider": "openai", "category": "embedding", "status": "active"},
        {"model_code": "text-embedding-3-small", "display_name": "Text Embedding 3 Small", "provider": "openai", "category": "embedding", "status": "active"},
        {"model_code": "dall-e-3", "display_name": "DALL-E 3", "provider": "openai", "category": "image", "status": "active"},
    ]

    print(f"\n--- Seeding {len(models)} models to catalog ---")
    for m in models:
        try:
            resp = client.post("/copilot/models/catalog", json=m)
            if resp.status_code in (200, 201):
                print(f"  [OK] {m['model_code']}")
            else:
                print(f"  [SKIP] {m['model_code']}: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            print(f"  [ERR] {m['model_code']}: {e}")


def seed_feature_catalog():
    """Seed feature catalog with standard entitlements."""
    features = [
        {"feature_key": "copilot_access", "display_name": "Copilot Access", "description": "Basic access to the AI copilot", "type": "boolean", "default_value": "true"},
        {"feature_key": "advanced_models", "display_name": "Advanced Models", "description": "Access to premium AI models (GPT-4o, Claude 3 Opus, etc.)", "type": "boolean", "default_value": "false"},
        {"feature_key": "custom_agents", "display_name": "Custom Agents", "description": "Ability to create and manage custom AI agents", "type": "boolean", "default_value": "false"},
        {"feature_key": "max_monthly_credits", "display_name": "Max Monthly Credits", "description": "Maximum monthly credit allocation", "type": "number", "default_value": "1000"},
        {"feature_key": "mcp_servers", "display_name": "MCP Server Connections", "description": "Connect to external MCP servers for tool use", "type": "boolean", "default_value": "false"},
        {"feature_key": "guardrails", "display_name": "Guardrails", "description": "Content filtering and safety guardrails", "type": "boolean", "default_value": "true"},
        {"feature_key": "marketplace_access", "display_name": "Marketplace Access", "description": "Access to the agent and tool marketplace", "type": "boolean", "default_value": "true"},
        {"feature_key": "api_playground", "display_name": "API Playground", "description": "Interactive API testing playground", "type": "boolean", "default_value": "false"},
        {"feature_key": "audit_logs", "display_name": "Audit Logs", "description": "Access to detailed audit and activity logs", "type": "boolean", "default_value": "true"},
        {"feature_key": "support_tickets", "display_name": "Support Tickets", "description": "Submit and track support tickets", "type": "boolean", "default_value": "true"},
    ]

    print(f"\n--- Seeding {len(features)} features to catalog ---")
    for f in features:
        fk = f["feature_key"]
        try:
            resp = client.put(f"/copilot/entitlements/catalog/{fk}", json=f)
            if resp.status_code in (200, 201):
                print(f"  [OK] {fk}")
            else:
                print(f"  [SKIP] {fk}: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            print(f"  [ERR] {fk}: {e}")


def seed_marketplace_listings():
    """Seed sample marketplace listings."""
    listings = [
        {
            "name": "Code Review Assistant",
            "description": "An AI-powered code review agent that analyzes pull requests and provides detailed feedback on code quality, security, and best practices.",
            "category": "developer_tools",
            "tags": ["code-review", "security", "best-practices"],
            "status": "published",
            "price": 0,
        },
        {
            "name": "Document Summarizer",
            "description": "Summarize long documents, reports, and articles into concise bullet points. Supports PDF, DOCX, and plain text.",
            "category": "productivity",
            "tags": ["summarization", "documents", "productivity"],
            "status": "published",
            "price": 0,
        },
        {
            "name": "SQL Query Builder",
            "description": "Natural language to SQL query generator. Describe what data you need and get optimized SQL queries for PostgreSQL, MySQL, and SQLite.",
            "category": "developer_tools",
            "tags": ["sql", "database", "query"],
            "status": "published",
            "price": 0,
        },
        {
            "name": "Meeting Notes Agent",
            "description": "Automatically generate structured meeting notes with action items, decisions, and follow-ups from meeting transcripts.",
            "category": "productivity",
            "tags": ["meetings", "notes", "action-items"],
            "status": "published",
            "price": 0,
        },
        {
            "name": "API Documentation Writer",
            "description": "Generate comprehensive API documentation from OpenAPI specs, code comments, and example requests/responses.",
            "category": "developer_tools",
            "tags": ["api", "documentation", "openapi"],
            "status": "draft",
            "price": 0,
        },
    ]

    print(f"\n--- Seeding {len(listings)} marketplace listings ---")
    for listing in listings:
        try:
            resp = client.post("/copilot/marketplace/listings", json=listing)
            if resp.status_code in (200, 201):
                print(f"  [OK] {listing['name']}")
            else:
                print(f"  [SKIP] {listing['name']}: {resp.status_code} {resp.text[:100]}")
        except Exception as e:
            print(f"  [ERR] {listing['name']}: {e}")


if __name__ == "__main__":
    print(f"Seeding copilot data to {BASE_URL}")
    seed_model_catalog()
    seed_feature_catalog()
    seed_marketplace_listings()
    print("\nDone.")
