#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
UI_DIR="${REPO_ROOT}/ui/litellm-dashboard"
PROXY_UI_DIR="${REPO_ROOT}/litellm/proxy/_experimental/out"

cd "${UI_DIR}"
npm run build

mkdir -p "${PROXY_UI_DIR}"
cp -r "${UI_DIR}/out/." "${PROXY_UI_DIR}/"

echo "UI build synced to ${PROXY_UI_DIR}"
