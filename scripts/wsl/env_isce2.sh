#!/usr/bin/env bash
# 供 WSL 桥接在执行 ISCE2/MintPy 前 source（Ubuntu conda isce2，不用 /mnt 下 Windows 源码）
set -e
if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
  conda activate isce2
fi
# 若 Snaphu 在自定义目录，可在此 export
# export SNAPHU_BIN=/path/to/snaphu/bin
export INSAR_PROJECT_ROOT="${INSAR_PROJECT_ROOT:-$HOME/insar-system}"
# topsStack：conda 安装位于 $CONDA_PREFIX/share/isce2/topsStack
if [[ -f "${CONDA_PREFIX}/share/isce2/topsStack/stackSentinel.py" ]]; then
  export INSAR_ISCE2_TOPS_STACK="${CONDA_PREFIX}/share/isce2/topsStack"
  export INSAR_ISCE2_STACK_PYTHONPATH="${CONDA_PREFIX}/share/isce2"
  export PATH="${INSAR_ISCE2_TOPS_STACK}:${PATH}"
  export PYTHONPATH="${INSAR_ISCE2_STACK_PYTHONPATH}:${PYTHONPATH:-}"
fi
# ISCE Python 包（dem.py 等）：site-packages/isce
if python3 -c "import isce" 2>/dev/null; then
  _isce_root="$(python3 -c "import os, isce; print(os.path.dirname(isce.__file__))")"
  if [[ -n "${_isce_root}" && -f "${_isce_root}/applications/dem.py" ]]; then
    export INSAR_WSL_ISCE2_MAIN="${_isce_root}"
  fi
fi
