#!/usr/bin/env bash
# If ISCE2/MintPy are not configured in WSL, run setup automatically.
# Run in WSL: bash scripts/wsl/ensure_env.sh
# Or from Windows: scripts\ensure_wsl_env.bat

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

check() {
  bash "$SCRIPT_DIR/check_env.sh"
}

echo "=== WSL ISCE2/MintPy: check and auto-setup if needed ==="
echo ""

if check; then
  echo ""
  echo "Environment already READY. No setup needed."
  exit 0
fi

echo ""
echo "Environment NOT READY. Running setup (Miniconda + isce2 + mintpy)..."
echo "This may take several minutes."
echo ""

bash "$SCRIPT_DIR/setup_isce2_ubuntu24.sh"

echo ""
echo "=== Verifying after setup ==="
echo ""
if check; then
  echo ""
  echo "Setup complete. You can start Desktop with scripts\\start_desktop_wsl.bat"
  exit 0
fi

echo ""
echo "Setup ran but check still failed. See messages above or docs/wsl_ubuntu24_isce2_setup.md"
exit 1
