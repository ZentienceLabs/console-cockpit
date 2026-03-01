#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[1/5] Python syntax checks"
python -m py_compile "$ROOT_DIR/alchemi/endpoints/control_plane_v1.py"

echo "[2/5] Security policy + auth tamper tests"
poetry run pytest "$ROOT_DIR/tests/alchemi_security/test_control_plane_security.py" -q

echo "[3/5] Concurrent load smoke"
poetry run pytest "$ROOT_DIR/tests/alchemi_security/test_control_plane_load_smoke.py" -q

echo "[4/5] UI type safety"
(
  cd "$ROOT_DIR/ui/litellm-dashboard"
  pnpm exec tsc --noEmit
)

echo "[5/5] Summary"
echo "Hardening campaign completed successfully."
