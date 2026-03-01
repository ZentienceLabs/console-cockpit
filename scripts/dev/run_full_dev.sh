#!/usr/bin/env bash
set -euo pipefail

# Runs backend + Next.js dashboard in dev mode.
# - Backend API: http://localhost:${PROXY_PORT}
# - UI dev:      http://localhost:${UI_PORT}
#
# Usage:
#   ./scripts/dev/run_full_dev.sh
# Optional env:
#   PROXY_PORT=4001 UI_PORT=4000 DISABLE_SCHEMA_UPDATE=true ./scripts/dev/run_full_dev.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
UI_DIR="${REPO_ROOT}/ui/litellm-dashboard"

PROXY_PORT="${PROXY_PORT:-4001}"
UI_PORT="${UI_PORT:-4000}"
DISABLE_SCHEMA_UPDATE="${DISABLE_SCHEMA_UPDATE:-true}"
DEBUG="${DEBUG:-false}"

# Litellm expects a strict boolean for --debug.
case "${DEBUG,,}" in
  true|false) ;;
  *)
    DEBUG="false"
    ;;
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

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${UI_PID:-}" ]]; then
    kill "${UI_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

cd "${REPO_ROOT}"
if info="$(port_in_use_info "${PROXY_PORT}")"; then
  echo "Port ${PROXY_PORT} is already in use."
  echo "${info}"
  exit 1
fi
if info="$(port_in_use_info "${UI_PORT}")"; then
  echo "Port ${UI_PORT} is already in use."
  echo "${info}"
  exit 1
fi

DISABLE_SCHEMA_UPDATE="${DISABLE_SCHEMA_UPDATE}" DEBUG="${DEBUG}" \
  poetry run litellm --port "${PROXY_PORT}" &
BACKEND_PID=$!

cd "${UI_DIR}"
NEXT_PUBLIC_PROXY_BASE_URL="http://localhost:${PROXY_PORT}" \
  npm run dev -- --port "${UI_PORT}" &
UI_PID=$!

echo "Backend PID: ${BACKEND_PID} (http://localhost:${PROXY_PORT})"
echo "UI PID: ${UI_PID} (http://localhost:${UI_PORT})"
echo "DISABLE_SCHEMA_UPDATE=${DISABLE_SCHEMA_UPDATE}"

wait -n "${BACKEND_PID}" "${UI_PID}"
