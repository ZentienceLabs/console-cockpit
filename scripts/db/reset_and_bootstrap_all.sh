#!/usr/bin/env bash
set -euo pipefail

# Reset + bootstrap script for:
# 1) console-cockpit DB (public + copilot)
# 2) alchemi-web app DB (public)
# 3) alchemi-ai APP DB add-on tables (workspace_api_keys + integration_connections)
#
# This is destructive. It drops schemas/tables.
#
# Example:
#   ./scripts/db/reset_and_bootstrap_all.sh \
#     --console-db-url "postgresql://..." \
#     --web-db-url "postgresql://..." \
#     --ai-app-db-url "postgresql://..." \
#     --yes

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
WS_ROOT="$(cd "${REPO_ROOT}/.." && pwd)"

CONSOLE_DB_URL="${CONSOLE_DB_URL:-}"
WEB_DB_URL="${WEB_DB_URL:-}"
AI_APP_DB_URL="${AI_APP_DB_URL:-}"
ALCHEMI_WEB_DIR="${ALCHEMI_WEB_DIR:-${WS_ROOT}/alchemi-web}"
ALCHEMI_AI_DIR="${ALCHEMI_AI_DIR:-${WS_ROOT}/alchemi-ai}"

CONFIRMED="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --console-db-url)
      CONSOLE_DB_URL="$2"
      shift 2
      ;;
    --web-db-url)
      WEB_DB_URL="$2"
      shift 2
      ;;
    --ai-app-db-url)
      AI_APP_DB_URL="$2"
      shift 2
      ;;
    --yes)
      CONFIRMED="true"
      shift 1
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "${CONFIRMED}" != "true" ]]; then
  echo "Refusing to run without explicit confirmation."
  echo "Re-run with --yes"
  exit 1
fi

if [[ -z "${CONSOLE_DB_URL}" || -z "${WEB_DB_URL}" || -z "${AI_APP_DB_URL}" ]]; then
  echo "Missing required DB URLs. Set via args or env:"
  echo "  CONSOLE_DB_URL"
  echo "  WEB_DB_URL"
  echo "  AI_APP_DB_URL"
  exit 1
fi

for cmd in psql npx pnpm poetry; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "Required command not found: ${cmd}" >&2
    exit 1
  fi
done

echo "==> [1/6] Reset console-cockpit DB schemas"
psql "${CONSOLE_DB_URL}" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT nspname
        FROM pg_namespace
        WHERE nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND nspname NOT LIKE 'pg_temp_%'
          AND nspname NOT LIKE 'pg_toast_temp_%'
    LOOP
        EXECUTE format('DROP SCHEMA IF EXISTS %I CASCADE', r.nspname);
    END LOOP;
END $$;

CREATE SCHEMA IF NOT EXISTS public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
SQL

echo "==> [2/6] Bootstrap console-cockpit base schema (Prisma db push)"
(
  cd "${REPO_ROOT}"
  DATABASE_URL="${CONSOLE_DB_URL}" npx prisma@6.16.2 db push --schema schema.prisma --skip-generate
)

echo "==> [3/6] Apply console-cockpit copilot SQL migrations"
for mig in \
  "${REPO_ROOT}/prisma/migrations/20260221100000_add_auth_org_id/migration.sql" \
  "${REPO_ROOT}/prisma/migrations/20260221200000_copilot_schema/migration.sql" \
  "${REPO_ROOT}/prisma/migrations/20260223153000_copilot_directory_backfill/migration.sql" \
  "${REPO_ROOT}/prisma/migrations/20260223183000_copilot_notification_support/migration.sql" \
  "${REPO_ROOT}/prisma/migrations/20260223194500_copilot_budget_hierarchy/migration.sql" \
  "${REPO_ROOT}/prisma/migrations/20260224010000_copilot_catalog_observability/migration.sql"; do
  if [[ ! -f "${mig}" ]]; then
    echo "Missing migration file: ${mig}" >&2
    exit 1
  fi
  psql "${CONSOLE_DB_URL}" -v ON_ERROR_STOP=1 -f "${mig}"
done

echo "==> [4/6] Reset alchemi-web app DB and force-sync models"
psql "${WEB_DB_URL}" -v ON_ERROR_STOP=1 <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO postgres;
GRANT ALL ON SCHEMA public TO public;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;
SQL

(
  cd "${ALCHEMI_WEB_DIR}"
  pnpm tsx scripts/db/force-sync-app-db.mjs --db-url "${WEB_DB_URL}"
)

echo "==> [5/6] Initialize alchemi-ai APP DB required tables"
(
  cd "${ALCHEMI_AI_DIR}"
  APP_POSTGRES_URI="${AI_APP_DB_URL}" poetry run python - <<'PY'
import asyncio
from gen_ui_backend.unapp.utils.workspace_key_store import init_workspace_keys_table
from gen_ui_backend.unapp.utils.integration_connections_store import init_integration_connections_table
from gen_ui_backend.unapp.utils.agent_db_store import init_agents_def_table

async def main():
    await init_workspace_keys_table()
    await init_integration_connections_table()
    await init_agents_def_table()
    print("OK: alchemi-ai APP DB table init completed")

asyncio.run(main())
PY
)

echo "==> [6/6] Verification summary"
psql "${CONSOLE_DB_URL}" -v ON_ERROR_STOP=1 -c "select table_schema, count(*) as table_count from information_schema.tables where table_schema in ('public','copilot') and table_type='BASE TABLE' group by table_schema order by table_schema;"
psql "${WEB_DB_URL}" -v ON_ERROR_STOP=1 -c "select count(*) as public_table_count from information_schema.tables where table_schema='public' and table_type='BASE TABLE';"
psql "${AI_APP_DB_URL}" -v ON_ERROR_STOP=1 -c "select table_name from information_schema.tables where table_schema='public' and table_name in ('workspace_api_keys','integration_connections','agents_def') order by table_name;"

echo "Done."
