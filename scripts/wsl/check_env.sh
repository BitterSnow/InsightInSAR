#!/usr/bin/env bash
# Check if ISCE2 and MintPy are correctly configured in WSL.
# Run in WSL: bash scripts/wsl/check_env.sh
# Or from Windows: scripts\check_wsl_env.bat

set -e
OK=0
FAIL=0

echo "=== WSL ISCE2 / MintPy environment check ==="
echo ""

# Optional: source env script (same as bridge uses)
if [[ -n "$INSAR_WSL_ENV_SCRIPT" && -f "$INSAR_WSL_ENV_SCRIPT" ]]; then
  echo "Sourcing: $INSAR_WSL_ENV_SCRIPT"
  source "$INSAR_WSL_ENV_SCRIPT" 2>/dev/null || true
elif [[ -f "$HOME/insar-wsl/env_isce2.sh" ]]; then
  echo "Sourcing: $HOME/insar-wsl/env_isce2.sh"
  source "$HOME/insar-wsl/env_isce2.sh" 2>/dev/null || true
elif [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  echo "Activating conda env isce2"
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
  conda activate isce2 2>/dev/null || true
fi

echo "--- ISCE2 ---"
if python -c "import isce; print('  OK:', isce.__file__)" 2>/dev/null; then
  ((OK++)) || true
else
  echo "  FAIL: cannot import isce (run setup_isce2_ubuntu24.sh or: conda create -n isce2 -c conda-forge isce2 -y)"
  ((FAIL++)) || true
fi

echo "--- MintPy ---"
if python -c "import mintpy; print('  OK:', mintpy.__file__)" 2>/dev/null; then
  ((OK++)) || true
else
  echo "  FAIL: cannot import mintpy (run setup_isce2_ubuntu24.sh or: conda install -c conda-forge mintpy -y)"
  ((FAIL++)) || true
fi

echo "--- Snaphu (optional) ---"
if command -v snaphu &>/dev/null; then
  echo "  OK: $(command -v snaphu)"
else
  echo "  (optional) not in PATH; unwrap step may need SNAPHU_BIN"
fi

echo ""
if [[ $FAIL -gt 0 ]]; then
  echo "Result: NOT READY ($OK ok, $FAIL failed). Configure ISCE2/MintPy in WSL (see docs/wsl_ubuntu24_isce2_setup.md)."
  exit 1
fi
echo "Result: READY (ISCE2 and MintPy OK)."
exit 0
