# DB Reset + Bootstrap

Script: `scripts/db/reset_and_bootstrap_all.sh`

## What it does

1. Resets `console-cockpit` DB and recreates:
   - `public` schema (LiteLLM/core tables)
   - `copilot` schema (Copilot management tables)
2. Applies required Copilot SQL migrations.
3. Resets `alchemi-web` app DB (`public`) and force-syncs Sequelize models.
4. Initializes `alchemi-ai` APP DB-required tables:
   - `workspace_api_keys`
   - `integration_connections`
   - `agents_def` (ensures indexes/triggers expected by AI helpers)

## Required inputs

Provide all 3 DB URLs via args or environment variables:

- `CONSOLE_DB_URL`
- `WEB_DB_URL`
- `AI_APP_DB_URL`

## Run

```bash
./scripts/db/reset_and_bootstrap_all.sh \
  --console-db-url "postgresql://..." \
  --web-db-url "postgresql://..." \
  --ai-app-db-url "postgresql://..." \
  --yes
```

## Notes

- This is destructive (`DROP SCHEMA ... CASCADE`), intended for fresh bootstrap only.
- `alchemi-web` sync uses `scripts/db/force-sync-app-db.mjs` to normalize known model/schema drift before force sync.
