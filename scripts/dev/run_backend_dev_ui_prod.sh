#!/usr/bin/env bash
set -euo pipefail

# Run backend in dev mode + UI in production mode.
#
# Usage:
#   ./scripts/dev/run_backend_dev_ui_prod.sh
# Optional env:
#   PROXY_PORT=4001 UI_PORT=4000 BUILD_UI=true DISABLE_SCHEMA_UPDATE=true ./scripts/dev/run_backend_dev_ui_prod.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

PROXY_PORT="${PROXY_PORT:-4001}"
UI_PORT="${UI_PORT:-4000}"
BUILD_UI="${BUILD_UI:-true}"
DISABLE_SCHEMA_UPDATE="${DISABLE_SCHEMA_UPDATE:-true}"

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

PROXY_PORT="${PROXY_PORT}" DISABLE_SCHEMA_UPDATE="${DISABLE_SCHEMA_UPDATE}" \
  ./scripts/dev/run_backend_dev.sh &
BACKEND_PID=$!

UI_PORT="${UI_PORT}" PROXY_PORT="${PROXY_PORT}" BUILD_UI="${BUILD_UI}" \
  ./scripts/dev/run_ui_prod.sh &
UI_PID=$!

echo "Backend (dev): http://localhost:${PROXY_PORT} (pid=${BACKEND_PID})"
echo "UI (prod):     http://localhost:${UI_PORT} (pid=${UI_PID})"
echo "DISABLE_SCHEMA_UPDATE=${DISABLE_SCHEMA_UPDATE} BUILD_UI=${BUILD_UI}"

wait -n "${BACKEND_PID}" "${UI_PID}"
