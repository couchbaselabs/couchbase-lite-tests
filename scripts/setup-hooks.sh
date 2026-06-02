#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

info()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# --- Python ---
if ! command -v python3 &>/dev/null; then
  fail "python3 not found. Install Python 3.10+ first."
fi

py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
py_major=$(echo "$py_version" | cut -d. -f1)
py_minor=$(echo "$py_version" | cut -d. -f2)
if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt 10 ]; }; then
  fail "Python 3.10+ required (found $py_version)."
fi
info "Python $py_version"

# --- uv ---
if ! command -v uv &>/dev/null; then
  warn "uv not found. Installing via pip..."
  python3 -m pip install --quiet uv || fail "Could not install uv."
  # pip may have installed uv into a user/site directory that isn't on PATH yet.
  if ! command -v uv &>/dev/null; then
    pip_user_base="$(python3 -m site --user-base 2>/dev/null)"
    if [ -n "$pip_user_base" ] && [ -x "$pip_user_base/bin/uv" ]; then
      export PATH="$pip_user_base/bin:$PATH"
      warn "Added $pip_user_base/bin to PATH for this session — add it to your shell rc for future runs."
    fi
  fi
  if ! command -v uv &>/dev/null; then
    fail "uv installed but not on PATH. Add $(python3 -m site --user-base)/bin (or the relevant Python scripts dir) to your PATH and re-run."
  fi
fi
info "uv $(uv --version 2>/dev/null || echo 'installed')"

# --- uv sync (before tool installs so the venv is ready) ---
cd "$REPO_ROOT"
echo ""
echo "Running uv sync..."
uv sync || fail "uv sync failed."
info "Dependencies synced"

# --- pre-commit (installed via uv tool to avoid polluting the project venv) ---
if ! command -v pre-commit &>/dev/null; then
  warn "pre-commit not found. Installing via uv tool..."
  uv tool install pre-commit || fail "Could not install pre-commit."
fi
info "pre-commit $(pre-commit --version 2>/dev/null)"

# --- detect-secrets (installed via uv tool) ---
if ! command -v detect-secrets &>/dev/null; then
  warn "detect-secrets not found. Installing via uv tool..."
  uv tool install detect-secrets || fail "Could not install detect-secrets."
fi
info "detect-secrets installed"

# --- Install git hooks ---
echo ""
echo "Installing git hooks..."
pre-commit install || fail "pre-commit install failed."
info "Git hooks installed (pre-commit)"

# --- Regenerate secrets baseline if missing ---
if [ ! -f "$REPO_ROOT/.secrets.baseline" ]; then
  warn ".secrets.baseline not found. Generating..."
  detect-secrets scan > "$REPO_ROOT/.secrets.baseline"
  info "Secrets baseline generated"
else
  info "Secrets baseline exists"
fi

echo ""
echo -e "${GREEN}Setup complete. All hooks are active.${NC}"
