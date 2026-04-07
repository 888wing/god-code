#!/bin/bash
# Install git hooks for the god-code repo.
#
# Run after cloning: ./scripts/install-hooks.sh
#
# Currently installs:
#   - pre-commit: runs gitleaks on staged changes to catch secret leaks
#     before they are committed. If gitleaks is not installed, the hook
#     warns and exits 0 (does not block commits).

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_DIR="$REPO_ROOT/.git/hooks"
HOOK_PATH="$HOOK_DIR/pre-commit"

mkdir -p "$HOOK_DIR"

cat > "$HOOK_PATH" <<'HOOK_EOF'
#!/bin/bash
# Pre-commit hook: scan staged changes for secrets.
# Installed by scripts/install-hooks.sh.
set -e

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "gitleaks not installed — skipping pre-commit secret scan."
  echo "Install with: brew install gitleaks"
  exit 0
fi

gitleaks protect --staged --config .gitleaks.toml --verbose
HOOK_EOF

chmod +x "$HOOK_PATH"

echo "Installed pre-commit hook at $HOOK_PATH"
echo "Test it by staging a change and running: git commit"
