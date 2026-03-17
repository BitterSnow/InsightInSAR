"""
MintPy smallbaselineApp facade: init work dir, get pipeline (step list), run single step or steps.
WSL only: runs inside WSL via run_mintpy_init_wsl / run_mintpy_wsl. For desktop time-series flow.
"""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
from typing import Any, Callable, Dict, List, Optional

# Paths
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_MINTPY_SRC = os.path.join(_PROJECT_ROOT, "lib", "MintPy-main", "src")
_MINTPY_DEFAULTS = os.path.join(_MINTPY_SRC, "mintpy", "defaults")
_TEMPLATE_DEFAULT = "smallbaselineApp.cfg"
_TEMPLATE_PATH = os.path.join(_MINTPY_DEFAULTS, _TEMPLATE_DEFAULT)

# Default 13 steps from processDDH.ipynb (desktop default workflow)
STEP_LIST_NOTEBOOK: List[str] = [
    "load_data",
    "modify_network",
    "reference_point",
    "correct_unwrap_error",
    "invert_network",
    "correct_SET",
    "correct_ionosphere",
    "correct_troposphere",
    "deramp",
    "correct_topography",
    "residual_RMS",
    "velocity",
    "geocode",
]

STEP_NAMES_CN: Dict[str, str] = {
    "load_data": "加载数据",
    "modify_network": "修改网络",
    "reference_point": "参考点",
    "quick_overview": "快速概览",
    "correct_unwrap_error": "解缠误差校正",
    "invert_network": "网络反演",
    "correct_LOD": "LOD 校正",
    "correct_SET": "SET 校正",
    "correct_ionosphere": "电离层校正",
    "correct_troposphere": "对流层校正",
    "deramp": "去斜",
    "correct_topography": "地形校正",
    "residual_RMS": "残差 RMS",
    "reference_date": "参考日期",
    "velocity": "速率",
    "geocode": "地理编码",
    "google_earth": "Google Earth",
    "hdfeos5": "HDF-EOS5",
}


def _find_stack_root(work_dir: str) -> Optional[str]:
    """
    When work_dir is .../mintpy, find the directory that contains merged/ and reference/
    (topsStack output). Tries: parent, parent/processing, parent/stack.
    """
    work_dir = os.path.abspath(work_dir)
    parent = os.path.dirname(work_dir)
    if os.path.basename(work_dir).lower() != "mintpy":
        return None
    candidates = [
        parent,
        os.path.join(parent, "processing"),
        os.path.join(parent, "stack"),
        os.path.join(parent, "processing", "stack"),
    ]
    for root in candidates:
        if not os.path.isdir(root):
            continue
        merged = os.path.join(root, "merged")
        ref = os.path.join(root, "reference")
        if os.path.isdir(merged) and os.path.isdir(ref):
            return root
    return None


def _validate_stack_paths(stack_root: str) -> tuple[bool, str]:
    """Check that stack_root contains expected topsStack dirs. Return (ok, warning_message)."""
    stack_root = os.path.abspath(stack_root)
    merged = os.path.join(stack_root, "merged")
    ref = os.path.join(stack_root, "reference")
    if not os.path.isdir(merged):
        return False, f"未找到目录 merged：{merged}\n请将「Stack 产品目录」设为 topsStack 输出根目录（含 merged、reference）。"
    if not os.path.isdir(ref):
        return False, f"未找到目录 reference：{ref}\n请确认 Stack 已跑完并生成 reference。"
    ref_xmls = glob.glob(os.path.join(ref, "IW*.xml")) or glob.glob(os.path.join(ref, "*.xml"))
    if not ref_xmls:
        return False, f"reference 下未找到 IW*.xml：{ref}\n请确认 Stack 参考景元数据已生成。"
    # Optional: warn if geometry or interferograms missing (user may not have run those steps yet)
    warnings = []
    geom = os.path.join(merged, "geom_reference", "hgt.rdr")
    if not os.path.isfile(geom):
        warnings.append("未找到 merged/geom_reference/hgt.rdr，请确认 Stack 已跑完几何步骤。")
    igrams = os.path.join(merged, "interferograms")
    if not os.path.isdir(igrams):
        warnings.append("未找到 merged/interferograms，请确认 Stack 已跑完干涉与解缠步骤。")
    if warnings:
        return True, "已写入路径。\n" + "\n".join(warnings)
    return True, ""


def init_mintpy_workdir(
    work_dir: str,
    stack_work_dir: Optional[str] = None,
    stack_product_dir: Optional[str] = None,
    custom_template_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create MintPy work dir and smallbaselineApp.cfg in WSL.
    work_dir may be Windows path; converted to WSL for init.
    """
    from backend.services import wsl_runner

    if not _use_wsl():
        return {"success": False, "error_message": "仅支持 WSL 模式。请设置 INSAR_USE_WSL=1 并用 scripts/start_desktop_wsl.bat 启动。"}

    work_dir_wsl = work_dir.rstrip("/")
    if work_dir and ("\\" in work_dir or (len(work_dir) >= 2 and work_dir[1] == ":")):
        work_dir_wsl = wsl_runner.windows_path_to_wsl(work_dir.replace("\\", "/").strip())

    project_root = wsl_runner.get_wsl_project_root()
    if not project_root:
        return {"success": False, "error_message": "WSL 模式下请设置 INSAR_WSL_PROJECT_ROOT"}
    init_json = json.dumps({
        "work_dir": work_dir_wsl,
        "stack_work_dir": (stack_work_dir or "").rstrip("/") or None,
        "stack_product_dir": (stack_product_dir or "").rstrip("/") or None,
        "custom_template_path": (custom_template_path or "").strip() or None,
    })
    cmd = f"cd '{project_root}' && PYTHONPATH='.' INSAR_PROJECT_ROOT='{project_root}' python3 -m backend.scripts.run_mintpy_init_wsl"
    result = wsl_runner.run_wsl(cmd, env_script=wsl_runner.get_wsl_env_script(), extra_env={"INSAR_MINTPY_INIT_JSON": init_json}, timeout=60)
    if not result.get("success"):
        out = (result.get("stdout") or "").strip()
        for line in reversed(out.splitlines()):
            if line.strip().startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    pass
        return {"success": False, "error_message": result.get("error_message", "WSL MintPy 初始化失败")}
    stdout = (result.get("stdout") or "").strip()
    for line in reversed(stdout.splitlines()):
        if line.strip().startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {"success": False, "error_message": "WSL 未返回有效结果"}


# Keys that are file/dir paths; do NOT rewrite processor, yes/no, etc.
_LOAD_PATH_KEYS = frozenset({
    "mintpy.load.metaFile", "mintpy.load.baselineDir",
    "mintpy.load.unwFile", "mintpy.load.corFile", "mintpy.load.connCompFile", "mintpy.load.intFile",
    "mintpy.load.ionUnwFile", "mintpy.load.ionCorFile", "mintpy.load.ionConnCompFile",
    "mintpy.load.demFile", "mintpy.load.lookupYFile", "mintpy.load.lookupXFile",
    "mintpy.load.incAngleFile", "mintpy.load.azAngleFile",
    "mintpy.load.shadowMaskFile", "mintpy.load.waterMaskFile", "mintpy.load.bperpFile",
})

# ISCE topsStack default relative paths (when template says "auto", we fill these under stack_root)
_ISCE_TOPS_AUTO_PATHS = {
    "mintpy.load.metaFile": "reference/IW*.xml",
    "mintpy.load.baselineDir": "baselines",
    "mintpy.load.unwFile": "merged/interferograms/*/filt*.unw",
    "mintpy.load.corFile": "merged/interferograms/*/filt*.cor",
    "mintpy.load.connCompFile": "merged/interferograms/*/filt*.unw.conncomp",
    "mintpy.load.intFile": "None",
    "mintpy.load.demFile": "merged/geom_reference/hgt.rdr",
    "mintpy.load.lookupYFile": "merged/geom_reference/lat.rdr",
    "mintpy.load.lookupXFile": "merged/geom_reference/lon.rdr",
    "mintpy.load.incAngleFile": "merged/geom_reference/los.rdr",
    "mintpy.load.azAngleFile": "merged/geom_reference/los.rdr",
    "mintpy.load.shadowMaskFile": "merged/geom_reference/shadowMask.rdr",
    "mintpy.load.waterMaskFile": "merged/geom_reference/waterMask.rdr",
    "mintpy.load.bperpFile": "None",
}


def _stack_path_join(stack_root: str, rel: str) -> str:
    """Join stack_root with relative path. Use '/' when stack_root is WSL path (starts with /)."""
    rel = rel.replace("\\", "/")
    if stack_root.startswith("/"):
        return (stack_root.rstrip("/") + "/" + rel).replace("//", "/")
    return os.path.join(stack_root, rel)


def _rewrite_template_paths_to_absolute(cfg_path: str, stack_root: str) -> None:
    """Rewrite mintpy.load.* path options to absolute paths under stack_root. Replace 'auto' with ISCE tops paths."""
    if not stack_root.startswith("/"):
        stack_root = os.path.abspath(stack_root)
    with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    out = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            out.append(line)
            continue
        if "mintpy.load." not in s or "=" not in s:
            out.append(line)
            continue
        key, _, rest = s.partition("=")
        key = key.strip()
        # Strip inline comment so val is only the value (e.g. "auto" not "auto  #[comment]")
        val = rest.split("#")[0].strip()
        # Never rewrite processor or non-path options
        if key not in _LOAD_PATH_KEYS:
            out.append(line)
            continue
        if not val or val.lower() == "none":
            out.append(line)
            continue
        # When value is "auto", use ISCE tops default path under stack_root
        if val.lower() == "auto" and key in _ISCE_TOPS_AUTO_PATHS:
            auto_val = _ISCE_TOPS_AUTO_PATHS[key]
            if auto_val == "None":
                out.append(f"{key} = None\n")
            else:
                out.append(f"{key} = {_stack_path_join(stack_root, auto_val)}\n")
            continue
        # Already a path: make absolute if relative (only if it looks like a path, not a keyword)
        if val.startswith("../"):
            val = _stack_path_join(stack_root, val[3:])
        elif not os.path.isabs(val) and (os.path.sep in val or "/" in val or "*" in val):
            # Exclude values that are keywords (e.g. "yes", "no", "default") - they have no path chars
            if val.lower() not in ("yes", "no", "default", "auto"):
                val = _stack_path_join(stack_root, val)
        out.append(f"{key} = {val}\n")
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.writelines(out)


def _merge_template(cfg_path: str, custom_path: str) -> None:
    """Update cfg_path with key=value from custom_path (only mintpy.* keys)."""
    with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
        cdict = _read_template_dict(f.read())
    with open(custom_path, "r", encoding="utf-8", errors="replace") as f:
        udict = _read_template_dict(f.read())
    for k, v in udict.items():
        if k.startswith("mintpy."):
            cdict[k] = v
    lines = []
    with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "=" in line and not line.strip().startswith("#"):
                key = line.split("=")[0].strip()
                if key in cdict:
                    lines.append(f"{key} = {cdict[key]}\n")
                    continue
            lines.append(line)
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _read_template_dict(content: str) -> Dict[str, str]:
    d: Dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        d[k.strip()] = v.strip()
    return d


def get_mintpy_pipeline(
    work_dir: str,
    use_full_list: bool = False,
) -> Dict[str, Any]:
    """
    Return step list for UI. Default: 13 steps from processDDH.ipynb.
    use_full_list: if True, use MintPy STEP_LIST (18 steps).
    """
    work_dir = os.path.abspath(work_dir)
    cfg_path = os.path.join(work_dir, _TEMPLATE_DEFAULT)
    if use_full_list:
        step_ids = [
            "load_data", "modify_network", "reference_point", "quick_overview",
            "correct_unwrap_error", "invert_network", "correct_LOD", "correct_SET",
            "correct_ionosphere", "correct_troposphere", "deramp", "correct_topography",
            "residual_RMS", "reference_date", "velocity", "geocode", "google_earth", "hdfeos5",
        ]
    else:
        step_ids = list(STEP_LIST_NOTEBOOK)
    steps = []
    for i, step_id in enumerate(step_ids):
        name_cn = STEP_NAMES_CN.get(step_id, step_id)
        steps.append({"id": step_id, "name": name_cn, "index": i})
    return {"work_dir": work_dir, "steps": steps, "template_exists": os.path.isfile(cfg_path)}


def _use_wsl() -> bool:
    try:
        from backend.services import wsl_runner
        return wsl_runner.use_wsl()
    except Exception:
        return False


def run_mintpy_step(
    work_dir: str,
    step_id: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Run one smallbaselineApp step in WSL via run_mintpy_wsl step.
    work_dir may be Windows path; converted to WSL for execution.
    """
    from backend.services import wsl_runner

    if not _use_wsl():
        return {"success": False, "error_message": "仅支持 WSL 模式。请设置 INSAR_USE_WSL=1 并用 scripts/start_desktop_wsl.bat 启动。", "step_id": step_id}

    work_dir_win = work_dir
    work_dir_wsl = work_dir.rstrip("/")
    if work_dir and ("\\" in work_dir or (len(work_dir) >= 2 and work_dir[1] == ":")):
        work_dir_wsl = wsl_runner.windows_path_to_wsl(work_dir.replace("\\", "/").strip())
    project_root = wsl_runner.get_wsl_project_root()
    if not project_root:
        return {"success": False, "error_message": "WSL 模式下请设置 INSAR_WSL_PROJECT_ROOT", "step_id": step_id}
    mintpy_src = f"{project_root.rstrip('/')}/lib/MintPy-main/src"
    cmd = (
        f"cd '{project_root}' && PYTHONPATH=\"{mintpy_src}:.:${{PYTHONPATH:-}}\" python3 -m backend.scripts.run_mintpy_wsl step"
        f" --work_dir='{work_dir_wsl}' --step_id='{step_id}'"
    )
    env_script = wsl_runner.get_wsl_env_script()
    extra = {
        "INSAR_MINTPY_STEP_WORK_DIR": work_dir_wsl,
        "INSAR_MINTPY_STEP_ID": step_id,
        "INSAR_PROJECT_ROOT": project_root,
    }
    out_line_count: List[int] = [0]

    def stream_cb(line: str) -> None:
        if progress_callback and line:
            out_line_count[0] += 1
            n = out_line_count[0]
            pct = min(5.0 + 90.0 * (1.0 - 1.0 / (1.0 + n * 0.02)), 95.0)
            progress_callback(pct, line.rstrip())

    result = wsl_runner.run_wsl(
        cmd,
        env_script=env_script,
        extra_env=extra,
        timeout=7200,
        stream_callback=stream_cb,
    )
    if progress_callback:
        progress_callback(100.0, f"步骤 {step_id} 完成")
    log_path_win = os.path.join(work_dir_win, "mintpy_step.log") if work_dir_win and ("\\" in work_dir_win or (len(work_dir_win) >= 2 and work_dir_win[1] == ":")) else (work_dir_wsl + "/mintpy_step.log")
    if result.get("success"):
        return {"success": True, "step_id": step_id}
    return {
        "success": False,
        "error_message": result.get("error_message", "WSL 执行失败"),
        "step_id": step_id,
        "log_file": log_path_win,
    }


def run_mintpy_steps(
    work_dir: str,
    from_step_index: int,
    step_ids: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """Run steps from from_step_index to end. step_ids defaults to STEP_LIST_NOTEBOOK."""
    if step_ids is None:
        step_ids = list(STEP_LIST_NOTEBOOK)
    total = len(step_ids) - from_step_index
    if total <= 0:
        if progress_callback:
            progress_callback(100.0, "无待执行步骤")
        return {"success": True}
    for i in range(from_step_index, len(step_ids)):
        step_id = step_ids[i]
        cur = i - from_step_index
        if progress_callback:
            progress_callback(100.0 * cur / total, f"步骤 {cur + 1}/{total}: {STEP_NAMES_CN.get(step_id, step_id)}")
        out = run_mintpy_step(work_dir, step_id, progress_callback=progress_callback)
        if not out.get("success"):
            return out
    if progress_callback:
        progress_callback(100.0, "全部步骤完成")
    return {"success": True}
