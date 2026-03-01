#!/usr/bin/env bash
set -euo pipefail

# Run dashboard UI in production mode (built assets), optionally rebuilding first.
#
# Usage:
#   ./scripts/dev/run_ui_prod.sh
# Optional env:
#   UI_PORT=4000 PROXY_PORT=4001 BUILD_UI=true ./scripts/dev/run_ui_prod.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
UI_DIR="${REPO_ROOT}/ui/litellm-dashboard"

UI_PORT="${UI_PORT:-4000}"
PROXY_PORT="${PROXY_PORT:-4001}"
BUILD_UI="${BUILD_UI:-true}"

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

cd "${UI_DIR}"

if info="$(port_in_use_info "${UI_PORT}")"; then
  echo "Port ${UI_PORT} is already in use. Stop the existing process first."
  echo "${info}"
  exit 1
fi

if [[ "${BUILD_UI,,}" == "true" ]]; then
  echo "Building UI with NEXT_PUBLIC_PROXY_BASE_URL=http://localhost:${PROXY_PORT}"
  NEXT_PUBLIC_PROXY_BASE_URL="http://localhost:${PROXY_PORT}" npm run build
fi

echo "Starting UI (prod) on http://localhost:${UI_PORT}"

# The dashboard uses Next static export (`output: "export"`), so `next start`
# is invalid. Serve `out/` instead.
if grep -Eq 'output:\s*["'"'"']export["'"'"']' next.config.mjs 2>/dev/null; then
  if [[ ! -d "out" ]]; then
    echo "Missing UI build output directory: ${UI_DIR}/out"
    echo "Run with BUILD_UI=true once to generate static assets."
    exit 1
  fi

  # Local static serving compatibility:
  # Exported HTML may reference assets at /litellm-asset-prefix/_next/... while
  # `out/` contains only `/_next/...`. Mirror that path for local `serve`.
  if grep -q '/litellm-asset-prefix/_next/' out/index.html 2>/dev/null; then
    mkdir -p out/litellm-asset-prefix
    ln -sfn ../_next out/litellm-asset-prefix/_next
  fi

  # Next static export emits top-level route files as `route.html`. In local
  # SPA serving mode, requests arrive as `/route` and may otherwise fall back
  # to `index.html`, which causes auth/page loops. Mirror file routes to
  # directory indexes (e.g. `out/login/index.html -> ../login.html`).
  shopt -s nullglob
  for html_file in out/*.html; do
    base_name="$(basename "${html_file}" .html)"
    if [[ "${base_name}" == "index" || "${base_name}" == "404" ]]; then
      continue
    fi
    mkdir -p "out/${base_name}"
    ln -sfn "../${base_name}.html" "out/${base_name}/index.html"
  done
  shopt -u nullglob

  # Compatibility aliases for backend-auth redirects that target /ui paths.
  # In split-port local mode, UI lives at root, so map /ui -> / and /ui/login -> /login.
  mkdir -p out/ui out/ui/login
  ln -sfn ../index.html out/ui/index.html
  ln -sfn ../../login.html out/ui/login/index.html

  # Safety shim: if any stale/local link sends SSO start to UI origin instead
  # of backend origin, forward it to backend to avoid 404.
  mkdir -p out/sso/key/generate
  cat > out/sso/key/generate/index.html <<EOF
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Redirecting...</title>
    <meta name="viewport" content="width=device-width,initial-scale=1" />
  </head>
  <body>
    <script>
      (function () {
        var target = "http://localhost:${PROXY_PORT}" + window.location.pathname + window.location.search + window.location.hash;
        window.location.replace(target);
      })();
    </script>
    Redirecting to authentication...
  </body>
</html>
EOF

  mkdir -p out/sso/callback
  cat > out/sso/callback/index.html <<EOF
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Redirecting...</title>
    <meta name="viewport" content="width=device-width,initial-scale=1" />
  </head>
  <body>
    <script>
      (function () {
        var target = "http://localhost:${PROXY_PORT}" + window.location.pathname + window.location.search + window.location.hash;
        window.location.replace(target);
      })();
    </script>
    Completing sign in...
  </body>
</html>
EOF

  # `serve -s` rewrites route paths like `/login` to `/index.html`, which
  # causes login redirect loops for exported Next routes. Use `http-server`
  # with html extension resolution so `/login` maps to `/login.html` or
  # `/login/index.html`.
  npx http-server@latest out -p "${UI_PORT}" -e html -c-1
else
  NEXT_PUBLIC_PROXY_BASE_URL="http://localhost:${PROXY_PORT}" \
    npm run start -- --port "${UI_PORT}"
fi
