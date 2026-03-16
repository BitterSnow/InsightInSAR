#!/usr/bin/env bash
# 供 WSL 桥接在执行 ISCE2/MintPy 前 source
set -e
if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
  conda activate isce2
fi
# 若 Snaphu 在自定义目录，可在此 export
# export SNAPHU_BIN=/path/to/snaphu/bin
# 项目代码路径（用于 Python 找 topsStack 等）
export INSAR_PROJECT_ROOT="${INSAR_PROJECT_ROOT:-$HOME/insar-system}"
export PYTHONPATH="${INSAR_PROJECT_ROOT}/lib/isce2-main/contrib/stack:${PYTHONPATH:-}"
