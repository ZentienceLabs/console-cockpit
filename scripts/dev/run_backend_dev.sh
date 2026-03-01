#!/usr/bin/env bash
set -euo pipefail

# Run LiteLLM backend in dev mode only.
#
# Usage:
#   ./scripts/dev/run_backend_dev.sh
# Optional env:
#   PROXY_PORT=4001 DISABLE_SCHEMA_UPDATE=true DEBUG=false ./scripts/dev/run_backend_dev.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROXY_PORT="${PROXY_PORT:-4001}"
DISABLE_SCHEMA_UPDATE="${DISABLE_SCHEMA_UPDATE:-true}"
DEBUG="${DEBUG:-false}"

case "${DEBUG,,}" in
  true|false) ;;
  *) DEBUG="false" ;;
esac

port_in_use_info() {
  local port="$1"
  local out=""
  if command -v ss >/dev/null 2>&1; then
    out="$(ss -ltnp 2>/dev/null | grep -E "[\:\.]${port}[[:space:]]" || true)"
    if [[ -n "${out}" ]]; then
      echo "${out}"
      return 0
    fi
  fi
  if command -v lsof >/dev/null 2>&1; then
    out="$(lsof -nP -iTCP:${port} -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${out}" ]]; then
      echo "${out}"
      return 0
    fi
  fi
  return 1
}

cd "${REPO_ROOT}"
if info="$(port_in_use_info "${PROXY_PORT}")"; then
  echo "Port ${PROXY_PORT} is already in use. Stop the existing process first."
  echo "${info}"
  exit 1
fi

echo "Starting backend on http://localhost:${PROXY_PORT}"
echo "DISABLE_SCHEMA_UPDATE=${DISABLE_SCHEMA_UPDATE}"
DISABLE_SCHEMA_UPDATE="${DISABLE_SCHEMA_UPDATE}" DEBUG="${DEBUG}" \
  poetry run litellm --port "${PROXY_PORT}"
