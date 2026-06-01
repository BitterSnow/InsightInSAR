#!/usr/bin/env bash
# 供 WSL 桥接在执行 ISCE2/MintPy 前 source（Ubuntu conda isce2，不用 /mnt 下 Windows 源码）
set +e
if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
  conda activate isce2 2>/dev/null
fi
export INSAR_PROJECT_ROOT="${INSAR_PROJECT_ROOT:-$HOME/insar-system}"
if [[ -n "${CONDA_PREFIX:-}" && -f "${CONDA_PREFIX}/share/isce2/topsStack/stackSentinel.py" ]]; then
  export INSAR_ISCE2_TOPS_STACK="${CONDA_PREFIX}/share/isce2/topsStack"
  export INSAR_ISCE2_STACK_PYTHONPATH="${CONDA_PREFIX}/share/isce2"
  export PATH="${INSAR_ISCE2_TOPS_STACK}:${PATH}"
  export PYTHONPATH="${INSAR_ISCE2_STACK_PYTHONPATH}:${PYTHONPATH:-}"
fi
# site-packages/isce（避免 source 时 import isce，首次导入可能 >20s 导致探针超时）
_py_ver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)"
if [[ -n "${CONDA_PREFIX:-}" && -n "${_py_ver}" ]]; then
  _isce_root="${CONDA_PREFIX}/lib/python${_py_ver}/site-packages/isce"
  if [[ -f "${_isce_root}/applications/dem.py" ]]; then
    export INSAR_WSL_ISCE2_MAIN="${_isce_root}"
  fi
fi
unset _py_ver _isce_root
set -e
