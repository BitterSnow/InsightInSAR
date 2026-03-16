#!/usr/bin/env bash
# WSL Ubuntu 24.04 下 ISCE2 + MintPy 环境安装脚本（可重复执行，用于验证或新实例）
# 用法：在 WSL 内执行 bash setup_isce2_ubuntu24.sh

set -e

INSTALL_DIR="${INSTALL_DIR:-$HOME}"
CONDA_ROOT="${CONDA_ROOT:-$INSTALL_DIR/miniconda3}"
ENV_NAME="${ENV_NAME:-isce2}"
ENV_SCRIPT_DIR="${ENV_SCRIPT_DIR:-$INSTALL_DIR/insar-wsl}"

echo "[setup] Install dir: $INSTALL_DIR, Conda: $CONDA_ROOT, env: $ENV_NAME"

# 1. Miniconda
if [[ ! -d "$CONDA_ROOT" ]]; then
  echo "[setup] Installing Miniconda to $CONDA_ROOT ..."
  cd "$INSTALL_DIR"
  wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O Miniconda3-latest-Linux-x86_64.sh
  bash Miniconda3-latest-Linux-x86_64.sh -b -p "$CONDA_ROOT"
  rm -f Miniconda3-latest-Linux-x86_64.sh
  echo "[setup] Conda installed. Run: $CONDA_ROOT/bin/conda init bash && source ~/.bashrc"
else
  echo "[setup] Conda already exists at $CONDA_ROOT"
fi

# 2. Activate conda (this script may run in subshell, so we source and run in same shell)
if [[ -f "$CONDA_ROOT/etc/profile.d/conda.sh" ]]; then
  source "$CONDA_ROOT/etc/profile.d/conda.sh"
else
  echo "[setup] Conda not found at $CONDA_ROOT. Install manually and re-run."
  exit 1
fi

# 3. Create env with isce2 + mintpy (only conda-forge to avoid Anaconda TOS prompt)
if conda env list | grep -q "^${ENV_NAME} "; then
  echo "[setup] Conda env '$ENV_NAME' already exists. Skipping create."
else
  echo "[setup] Creating conda env '$ENV_NAME' with isce2 and mintpy ..."
  conda create -n "$ENV_NAME" --override-channels -c conda-forge python=3.11 isce2 mintpy -y
fi

conda activate "$ENV_NAME"

# 4. Verify
echo "[setup] Verifying imports ..."
python -c "import isce; print('ISCE2:', isce.__file__)" || true
python -c "import mintpy; print('MintPy:', mintpy.__file__)" || true

# 5. Snaphu (optional)
if command -v snaphu &>/dev/null; then
  echo "[setup] snaphu found: $(command -v snaphu)"
else
  echo "[setup] snaphu not in PATH. Install via apt (snaphu) or set SNAPHU_BIN later."
fi

# 6. env_isce2.sh for bridge
mkdir -p "$ENV_SCRIPT_DIR"
ENV_SCRIPT="$ENV_SCRIPT_DIR/env_isce2.sh"
cat > "$ENV_SCRIPT" << ENVEOF
#!/usr/bin/env bash
# Sourced by WSL bridge before running ISCE2/MintPy commands
set -e
if [[ -f "$CONDA_ROOT/etc/profile.d/conda.sh" ]]; then
  source "$CONDA_ROOT/etc/profile.d/conda.sh"
  conda activate $ENV_NAME
fi
# INSAR_PROJECT_ROOT and PYTHONPATH are set by the bridge when invoking
ENVEOF
chmod +x "$ENV_SCRIPT"
echo "[setup] Wrote $ENV_SCRIPT"

echo "[setup] Done. To use: source $ENV_SCRIPT (or set INSAR_WSL_ENV_SCRIPT=$ENV_SCRIPT for the bridge)."
