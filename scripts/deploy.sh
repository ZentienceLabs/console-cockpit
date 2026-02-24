#!/usr/bin/env bash
#
# Alchemi Studio Console - Deployment Script
#
# Syncs the Alchemi schema and migrations into litellm_proxy_extras, then
# runs Prisma migrations against the target database. This is the standard
# way to deploy to any environment (dev, devtest, stage, prod).
#
# Usage:
#   ./scripts/deploy.sh                  # Full deploy (sync + migrate + build UI + start)
#   ./scripts/deploy.sh migrate          # Only run schema sync + DB migration
#   ./scripts/deploy.sh build-ui         # Only rebuild and copy the admin UI
#   ./scripts/deploy.sh start            # Only start the proxy server
#
# Environment:
#   DATABASE_URL    (required) PostgreSQL connection string for the target environment
#   PORT            (optional) Port to start the proxy on (default: 4000)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

PORT="${PORT:-4000}"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $*"; }
err()  { echo -e "${RED}[deploy]${NC} $*" >&2; }

# ─────────────────────────────────────────────
# Activate Poetry venv if not already in one
# ─────────────────────────────────────────────
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    log "Activating Poetry virtualenv..."
    set +u
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.venv/bin/activate"
    set -u
fi

load_env_file_safely() {
    local env_file="$1"
    while IFS= read -r raw_line || [ -n "$raw_line" ]; do
        # Trim leading/trailing whitespace
        local line
        line="$(echo "$raw_line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"

        # Skip comments/empty lines
        [ -z "$line" ] && continue
        [[ "$line" == \#* ]] && continue

        # Support optional "export KEY=VALUE"
        line="${line#export }"
        [[ "$line" != *=* ]] && continue

        local key="${line%%=*}"
        local value="${line#*=}"
        key="$(echo "$key" | sed -e 's/[[:space:]]*$//')"

        # Strip matching single/double quotes without evaluating the value.
        if [[ "$value" == \"*\" && "$value" == *\" ]]; then
            value="${value:1:${#value}-2}"
        elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
            value="${value:1:${#value}-2}"
        fi

        export "$key=$value"
    done < "$env_file"
}

# Load .env file if present and DATABASE_URL not already set
if [ -z "${DATABASE_URL:-}" ] && [ -f "$PROJECT_ROOT/.env" ]; then
    load_env_file_safely "$PROJECT_ROOT/.env"
fi

# ─────────────────────────────────────────────
# Find the litellm_proxy_extras package directory
# ─────────────────────────────────────────────
find_extras_dir() {
    local extras_dir
    extras_dir=$(python3 -c "import litellm_proxy_extras, os; print(os.path.dirname(litellm_proxy_extras.__file__))" 2>/dev/null) || true

    if [ -z "$extras_dir" ] || [ ! -d "$extras_dir" ]; then
        err "litellm_proxy_extras package not found. Run: poetry install -E proxy -E extra_proxy"
        exit 1
    fi
    echo "$extras_dir"
}

# ─────────────────────────────────────────────
# sync_schema: Copy schema + migrations into litellm_proxy_extras
# ─────────────────────────────────────────────
sync_schema() {
    log "Syncing schema and migrations..."

    local extras_dir
    extras_dir=$(find_extras_dir)
    local extras_migrations="$extras_dir/migrations"

    # 1. Sync schema.prisma to all locations
    cp "$PROJECT_ROOT/schema.prisma" "$PROJECT_ROOT/litellm/proxy/schema.prisma"
    cp "$PROJECT_ROOT/schema.prisma" "$extras_dir/schema.prisma"
    log "  schema.prisma synced to litellm/proxy/ and litellm_proxy_extras/"

    # 2. Copy Alchemi migrations into litellm_proxy_extras
    for migration_dir in "$PROJECT_ROOT"/prisma/migrations/*/; do
        local migration_name
        migration_name=$(basename "$migration_dir")
        local target="$extras_migrations/$migration_name"

        if [ ! -d "$target" ]; then
            cp -r "$migration_dir" "$target"
            log "  Migration added: $migration_name"
        else
            # Update existing migration SQL if source is newer
            if [ "$migration_dir/migration.sql" -nt "$target/migration.sql" ]; then
                cp "$migration_dir/migration.sql" "$target/migration.sql"
                log "  Migration updated: $migration_name"
            fi
        fi
    done

    log "Schema sync complete."
}

# ─────────────────────────────────────────────
# run_migrations: Apply pending migrations to the database
# ─────────────────────────────────────────────
run_migrations() {
    if [ -z "${DATABASE_URL:-}" ]; then
        err "DATABASE_URL is not set. Export it before running migrations."
        err "  export DATABASE_URL='postgresql://user:pass@host:5432/dbname'"
        exit 1
    fi

    log "Running database migrations..."

    local extras_dir
    extras_dir=$(find_extras_dir)

    # Generate Prisma client
    log "  Generating Prisma client..."
    prisma generate --schema="$PROJECT_ROOT/schema.prisma" 2>&1 | tail -1

    # Run prisma migrate deploy from the extras directory (where all migrations live)
    log "  Applying pending migrations..."
    local original_dir
    original_dir=$(pwd)
    cd "$extras_dir"
    prisma migrate deploy --schema="$extras_dir/schema.prisma" 2>&1
    cd "$original_dir"

    log "Migrations complete."
}

# ─────────────────────────────────────────────
# build_ui: Build the Next.js admin dashboard
# ─────────────────────────────────────────────
build_ui() {
    log "Building admin UI..."

    cd "$PROJECT_ROOT/ui/litellm-dashboard"
    npm install --prefer-offline 2>&1 | tail -1
    npm run build 2>&1

    log "  Copying build output to proxy static directory..."
    rm -rf "$PROJECT_ROOT/litellm/proxy/_experimental/out"
    cp -r out "$PROJECT_ROOT/litellm/proxy/_experimental/out"

    cd "$PROJECT_ROOT"
    log "UI build complete."
}

# ─────────────────────────────────────────────
# start_server: Start the LiteLLM proxy
# ─────────────────────────────────────────────
start_server() {
    log "Starting Alchemi Studio Console on port $PORT..."
    exec litellm --port "$PORT"
}

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────
cmd="${1:-all}"

case "$cmd" in
    migrate)
        sync_schema
        run_migrations
        ;;
    build-ui)
        build_ui
        ;;
    start)
        start_server
        ;;
    all)
        sync_schema
        run_migrations
        build_ui
        start_server
        ;;
    *)
        err "Unknown command: $cmd"
        echo "Usage: $0 {migrate|build-ui|start|all}"
        exit 1
        ;;
esac
