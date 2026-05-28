"""
ISCE2 topsStack pipeline: init (stackSentinel.py), parse run_xx to pipeline.json,
execute steps inside WSL only. Desktop flow control via wsl_runner (no local Windows ISCE2).
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Callable, Dict, List, Optional

from shared_models import StackConfigRequest

def _use_wsl() -> bool:
    from backend.services import wsl_runner
    return wsl_runner.use_wsl()

_WSL_REQUIRED_MSG = (
    "仅支持 WSL 模式。请设置 INSAR_USE_WSL=1 并用 scripts/start_desktop_wsl.bat 启动，"
    "或运行「InSAR WSL 部署向导」完成环境配置。"
)

# Paths
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PIPELINE_JSON = "pipeline.json"
_PIPELINE_STATE_JSON = "pipeline_state.json"
_RUN_FILES_DIR = "run_files"
_CONFIGS_DIR = "configs"

# WSL 下若未 source 带 numpy/ISCE2 的环境会报 ModuleNotFoundError，提示设置环境脚本
_WSL_ENV_HINT = (
    "WSL 内需使用带 numpy/ISCE2 的 Python。请设置环境变量 INSAR_WSL_ENV_SCRIPT 为 WSL 路径，"
    "指向激活 conda isce2 的脚本（如 /home/你的用户名/insar-wsl/env_isce2.sh）。"
    "参见 docs/wsl_ubuntu24_isce2_setup.md 第 6 节。"
)


def _wsl_env_hint_if_import_error(stderr: str) -> str:
    # 仅对缺少 numpy/isce 的报错提示设置 env 脚本（topsStack 等为 PYTHONPATH 问题）
    if not stderr:
        return ""
    if "No module named 'numpy'" not in stderr and "No module named 'isce" not in stderr:
        return ""
    return "\n\n" + _WSL_ENV_HINT


# run_xx filename (base) -> Chinese step name
STACK_STEP_NAMES: Dict[str, str] = {
    "run_01_unpack_topo_reference": "解压参考景",
    "run_02_unpack_secondary_slc": "解压从景",
    "run_03_average_baseline": "平均基线",
    "run_04_extract_burst_overlaps": "提取 burst 重叠",
    "run_05_overlap_geo2rdr": "重叠区 geo2rdr",
    "run_06_overlap_resample": "重叠区重采样",
    "run_07_pairs_misreg": "像对配准",
    "run_08_timeseries_misreg": "时序配准",
    "run_09_fullBurst_geo2rdr": "全 burst geo2rdr",
    "run_10_fullBurst_resample": "全 burst 重采样",
    "run_11_extract_stack_valid_region": "提取堆栈有效区",
    "run_12_merge_reference_secondary_slc": "合并参考与从景 SLC",
    "run_13_grid_baseline": "基线网格",
    "run_14_merge_reference_secondary_slc": "合并参考与从景 SLC",
    "run_15_grid_baseline": "基线网格",
    "run_16_generate_burst_igram": "生成 burst 干涉图",
    "run_17_merge_burst_igram": "合并 burst 干涉图",
    "run_18_filter_coherence": "滤波与相干",
    "run_19_unwrap": "解缠",
}
# Allow run_XX_<suffix> pattern for any number
for i in range(1, 25):
    for suffix, name in [
        ("generate_burst_igram", "生成 burst 干涉图"),
        ("merge_burst_igram", "合并 burst 干涉图"),
        ("filter_coherence", "滤波与相干"),
        ("unwrap", "解缠"),
    ]:
        key = "run_{:02d}_{}".format(i, suffix)
        if key not in STACK_STEP_NAMES:
            STACK_STEP_NAMES[key] = name


def _get_stack_step_timeout() -> Optional[int]:
    """
    单步超时（秒），可选安全上限。
    默认 None：不设超时。建议对长时间步骤设置 INSAR_STACK_STEP_TIMEOUT（如 28800=8 小时）作为兜底。
    """
    v = (os.environ.get("INSAR_STACK_STEP_TIMEOUT") or "").strip()
    if not v:
        return None
    try:
        return max(60, int(v))
    except ValueError:
        return None


def _get_stack_step_idle_timeout() -> Optional[int]:
    """
    输出空闲超时（秒）：连续无新 stdout 超过该时间则杀进程并视为成功。
    默认 None（关闭）：step 内常有多 burst/多景，burst 间可能长时间无输出，启用会误杀（如 step1 只跑一个 burst 就停）。
    已通过 SentinelWrapper/run_stack_wsl 显式 os._exit 保证进程结束，故默认仅以进程退出为结束。
    若遇“数据出完但进程不退出”可设 INSAR_STACK_STEP_IDLE_TIMEOUT（如 300）作为兜底。
    """
    v = (os.environ.get("INSAR_STACK_STEP_IDLE_TIMEOUT") or "").strip()
    if not v:
        return None
    try:
        return max(30, int(v))
    except ValueError:
        return None


def _bbox_to_str(bbox_snwe: Optional[List[float]]) -> Optional[str]:
    if not bbox_snwe or len(bbox_snwe) != 4:
        return None
    return " ".join(str(x) for x in bbox_snwe)


def _append_step_idle_note(work_dir_win: str, step_id: str, idle_timeout: int) -> None:
    """步骤因「输出空闲」结束时，在 stack_step.log 末尾追加说明（数据已出完、进程未退出时由空闲超时结束）。"""
    try:
        log_path = os.path.join(work_dir_win, "stack_step.log")
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write("\n")
            f.write("=" * 60 + "\n")
            f.write(f"[{step_id}] 按输出空闲结束（连续 {idle_timeout} 秒无新输出，已杀进程，步骤视为成功）\n")
            f.write("可调整 INSAR_STACK_STEP_IDLE_TIMEOUT（秒）改变空闲判定时间。\n")
    except OSError:
        pass


def stack_init(
    request: StackConfigRequest,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Run stackSentinel.py in WSL to generate configs + run_files in work_dir.
    work_dir/slc/orbit/dem/aux from UI (Windows paths) are converted to WSL paths.
    """
    from backend.services import wsl_runner

    if not _use_wsl():
        return {"success": False, "error_message": _WSL_REQUIRED_MSG, "pipeline": None, "log_file": None}

    work_dir_win = None
    raw = request.work_dir.rstrip("/").replace("\\", "/")
    if raw and len(raw) >= 2 and raw[1] == ":":
        work_dir_win = os.path.normpath(request.work_dir)
        work_dir = wsl_runner.windows_path_to_wsl(raw)
    else:
        work_dir = raw or request.work_dir
    if progress_callback:
        progress_callback(0.0, "准备 stackSentinel 参数…")

    wsl_runner.ensure_drives_for_paths(
        request.slc_dir,
        request.orbit_dir,
        request.aux_dir,
        request.dem_path,
        request.work_dir,
    )
    slc_win = os.path.abspath(request.slc_dir)
    slc_dir, slc_err = wsl_runner.resolve_windows_path_to_wsl(slc_win)
    if slc_err or not slc_dir:
        return {
            "success": False,
            "error_message": slc_err or f"SLC 目录在 WSL 中不可访问：{slc_win}",
            "pipeline": None,
            "log_file": None,
        }
    for label, path in (
        ("轨道", request.orbit_dir),
        ("Aux", request.aux_dir),
    ):
        wsl_p, err = wsl_runner.resolve_windows_path_to_wsl(os.path.abspath(path))
        if err or not wsl_p:
            return {
                "success": False,
                "error_message": err or f"{label} 路径在 WSL 中不可访问：{path}",
                "pipeline": None,
                "log_file": None,
            }
    dem_win = os.path.abspath(request.dem_path)
    if not os.path.isfile(dem_win):
        return {
            "success": False,
            "error_message": f"DEM 文件不存在：{dem_win}",
            "pipeline": None,
            "log_file": None,
        }
    dem_path = wsl_runner.windows_path_to_wsl(dem_win)
    orbit_dir = wsl_runner.windows_path_to_wsl(os.path.abspath(request.orbit_dir))
    aux_dir = wsl_runner.windows_path_to_wsl(os.path.abspath(request.aux_dir))
    swaths_to_use = request.swaths
    orbit_preflight_result: Optional[Dict[str, Any]] = None

    # 预检并补全精密星历（ASF POEORB）：解析各 SAFE 成像时刻，缺失则自动下载到 orbit_dir
    try:
        from backend.services.sentinel_orbit_asf import (
            ensure_precise_orbits_for_stack,
            format_orbit_preflight_for_ui,
        )

        def _orbit_progress(p: float, msg: str) -> None:
            if progress_callback:
                progress_callback(min(4.0, float(p)), msg)

        pre = ensure_precise_orbits_for_stack(
            os.path.abspath(request.slc_dir),
            os.path.abspath(request.orbit_dir),
            progress_callback=_orbit_progress if progress_callback else None,
        )
        orbit_preflight_result = pre
        if not pre.get("ok"):
            detail = format_orbit_preflight_for_ui(pre)
            err = (pre.get("message") or "精密星历预检失败") + "\n\n" + detail
            return {
                "success": False,
                "error_message": err,
                "pipeline": None,
                "log_file": None,
                "orbit_preflight": pre,
            }
        if progress_callback and pre.get("downloaded"):
            dl = pre["downloaded"]
            tail = ", ".join(dl[:8]) + (" …" if len(dl) > 8 else "")
            progress_callback(4.5, f"已从 ASF 下载 {len(dl)} 个精密星历: {tail}")
    except Exception as e:
        return {
            "success": False,
            "error_message": f"轨道预检异常: {e}",
            "pipeline": None,
            "log_file": None,
        }

    # 在 WSL 内执行 backend.scripts.run_stack_wsl init，参数通过 INSAR_STACK_INIT_JSON 传入
    project_root = wsl_runner.get_wsl_project_root()
    if not project_root:
        return {"success": False, "error_message": "WSL 模式下请设置 INSAR_WSL_PROJECT_ROOT（WSL 侧项目路径）", "pipeline": None, "log_file": None}
    isce_env, isce_env_err = wsl_runner.build_wsl_isce2_extra_env()
    if isce_env_err or not isce_env:
        return {
            "success": False,
            "error_message": isce_env_err or "未找到 WSL conda ISCE2 环境。",
            "pipeline": None,
            "log_file": None,
        }
    extra_env: Dict[str, str] = {
        "INSAR_STACK_INIT_JSON": "",
        "INSAR_PROJECT_ROOT": project_root,
        **isce_env,
    }
    init_json = json.dumps({
        "work_dir": work_dir,
        "slc_dir": slc_dir,
        "orbit_dir": orbit_dir,
        "dem_path": dem_path,
        "aux_dir": aux_dir,
        "polarization": request.polarization,
        "workflow": request.workflow,
        "swaths": swaths_to_use,
        "coregistration": request.coregistration,
        "num_connections": request.num_connections,
        "num_process": request.num_process,
        "bbox": _bbox_to_str(request.bbox_snwe) or "",
        "reference_date": request.reference_date or "",
        "exclude_dates": request.exclude_dates or "",
        "include_dates": request.include_dates or "",
        "start_date": request.start_date or "",
        "stop_date": request.stop_date or "",
    })
    cmd = f"cd '{project_root}' && PYTHONPATH=\".:${{PYTHONPATH:-}}\" python3 -m backend.scripts.run_stack_wsl init"
    env_script = wsl_runner.get_wsl_env_script()
    if progress_callback:
        progress_callback(5.0, "在 WSL 中运行 stackSentinel…")
    extra_env["INSAR_STACK_INIT_JSON"] = init_json
    result = wsl_runner.run_wsl(
        cmd,
        env_script=env_script,
        extra_env=extra_env,
        timeout=3600,
    )
    log_path_win = os.path.join(work_dir_win, "stack_init.log") if work_dir_win else None
    log_path_return = log_path_win or (work_dir + "/stack_init.log")

    stderr_str = result.get("stderr") or ""
    err_hint = _wsl_env_hint_if_import_error(stderr_str)

    def _write_wsl_log():
        if not log_path_win:
            return
        try:
            os.makedirs(work_dir_win, exist_ok=True)
            with open(log_path_win, "w", encoding="utf-8", errors="replace") as f:
                f.write("WSL stack_init\n")
                f.write("Env script: %s\n" % (env_script or "(none)"))
                f.write("Command: cd ... && python3 -m backend.scripts.run_stack_wsl init\n")
                f.write("Return: %s\n" % result.get("returncode", ""))
                f.write("--- stdout ---\n")
                f.write(result.get("stdout") or "")
                f.write("\n--- stderr ---\n")
                f.write(stderr_str)
                if err_hint:
                    f.write("\n")
                    f.write(err_hint.strip())
        except OSError:
            pass

    _write_wsl_log()
    if not result.get("success"):
        err_msg = result.get("error_message") or stderr_str or "WSL 执行失败"
        if err_hint:
            err_msg = err_msg.rstrip() + err_hint
        if "fetchOrbit" in err_msg:
            err_msg += (
                "\n\n说明：topsStack 需将 $CONDA_PREFIX/share/isce2 加入 PYTHONPATH（import topsStack），"
                "并将 topsStack 目录加入 PATH（fetchOrbit.py）。请重启桌面后重试。"
                " 若已自动补全星历仍失败，请检查 WSL 内 INSAR_WSL_PROJECT_ROOT 是否指向包含 lib/isce2-main 的安装树。"
            )
        return {
            "success": False,
            "error_message": err_msg,
            "pipeline": None,
            "log_file": log_path_return,
        }
    stdout = (result.get("stdout") or "").strip()
    pipeline = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                pipeline = data.get("pipeline")
                break
            except json.JSONDecodeError:
                continue
    if not pipeline:
        return {"success": False, "error_message": "WSL 未返回 pipeline", "pipeline": None, "log_file": log_path_return}
    if progress_callback:
        progress_callback(100.0, "流程初始化完成")
    out: Dict[str, Any] = {
        "success": True,
        "pipeline": pipeline,
        "work_dir": work_dir_win or work_dir,
        "log_file": log_path_return,
    }
    if orbit_preflight_result:
        out["orbit_preflight"] = orbit_preflight_result
    return out


def parse_run_files_to_pipeline(work_dir: str) -> Optional[Dict[str, Any]]:
    """
    Scan work_dir/run_files for run_* files, sort by name; each file = one step.
    Return {"work_dir": work_dir, "steps": [{"id": "run_01", "name": "解压参考景", "commands": ["SentinelWrapper.py -c configs/..."]}, ...]}.
    """
    run_dir = os.path.join(work_dir, _RUN_FILES_DIR)
    if not os.path.isdir(run_dir):
        return None
    run_files: List[str] = []
    for name in os.listdir(run_dir):
        if name.startswith("run_") and not os.path.isdir(os.path.join(run_dir, name)):
            run_files.append(name)
    run_files.sort()
    steps = []
    for rname in run_files:
        path = os.path.join(run_dir, rname)
        commands: List[str] = []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Line is e.g. "SentinelWrapper.py -c /abs/path/config" or "SentinelWrapper.py -c configs/config_reference"
                commands.append(line)
        step_id = rname
        name = STACK_STEP_NAMES.get(rname, rname)
        steps.append({"id": step_id, "name": name, "commands": commands})
    return {"work_dir": work_dir, "steps": steps}


# 步骤 id -> 该步产出的相对目录（用于「清理本步输出」）。仅列出可安全删除的顶层或明确子目录。
_STACK_STEP_OUTPUT_DIRS: Dict[str, List[str]] = {
    "run_01_unpack_topo_reference": ["reference", "geom_reference"],
    "run_02_unpack_secondary_slc": ["secondary"],
    "run_03_average_baseline": ["baselines"],
    "run_04_extract_burst_overlaps": ["overlap"],
    "run_05_overlap_geo2rdr": ["overlap"],
    "run_06_overlap_resample": ["overlap"],
    "run_07_pairs_misreg": ["coreg_secondarys"],
    "run_08_timeseries_misreg": ["coreg_secondarys"],
    "run_09_fullBurst_geo2rdr": ["geom_reference"],
    "run_10_fullBurst_resample": ["coreg_secondarys"],
    "run_11_extract_stack_valid_region": ["stack"],
    "run_12_merge_reference_secondary_slc": [],
    "run_13_grid_baseline": [],
    "run_14_merge_reference_secondary_slc": [],
    "run_15_grid_baseline": [],
    "run_16_generate_burst_igram": ["merged/interferograms"],
    "run_17_merge_burst_igram": ["merged/interferograms"],
    "run_18_filter_coherence": ["merged/interferograms"],
    "run_19_unwrap": ["merged/interferograms"],
}


def get_stack_step_output_dirs(step_id: str) -> List[str]:
    """返回该步骤对应的输出相对目录列表（用于桌面端「清理本步输出」）。"""
    if not step_id:
        return []
    # 精确匹配
    if step_id in _STACK_STEP_OUTPUT_DIRS:
        return list(_STACK_STEP_OUTPUT_DIRS[step_id])
    # run_XX_* 模式取第一个匹配
    for key, dirs in _STACK_STEP_OUTPUT_DIRS.items():
        if key.startswith(step_id) or step_id.startswith(key.split("_")[0] + "_" + key.split("_")[1]):
            return list(dirs)
    return []


def clear_stack_step_output(work_dir: str, step_id: str) -> None:
    """删除该步骤在 work_dir 下的输出目录（Windows 路径时直接删，与 WSL 联动）。"""
    dirs = get_stack_step_output_dirs(step_id)
    work_dir = os.path.abspath(work_dir.replace("/", os.sep))
    for rel in dirs:
        path = os.path.join(work_dir, rel.replace("/", os.sep))
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
            except OSError:
                pass


def run_stack_step(
    work_dir: str,
    step_id: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    Execute one step by running each command via Python subprocess (no shell).
    Each command line is parsed as SentinelWrapper.py -c <config_path>; config_path is relative to work_dir.
    Stdout/stderr are streamed to progress_callback so the UI shows live log; progress moves 5%–95% as lines are received.
    Step1 (run_01) runs Sentinel1_TOPS (reference unpack) + topo (DEM/geometry), so long runtime is expected.
    When INSAR_USE_WSL=1: work_dir may be Windows path (from UI); convert to WSL and run in WSL.

    步骤结束检测（便于维护）:
    - 优先：输出空闲结束。连续无新 stdout 超过 INSAR_STACK_STEP_IDLE_TIMEOUT（默认 120 秒）则视为步骤结束，杀进程并返回成功。
      用于“数据已出完、控制台不刷新但子进程不退出”的情况，比仅依赖进程退出更可靠。
    - 其次：进程退出。poll() 非 None 时正常结束。
    - 兜底：INSAR_STACK_STEP_TIMEOUT 为可选硬超时，超时后杀进程并报失败。
    - 检测方式：proc.poll() 每 0.25s 轮询，并检查 last_output_time 与 idle_timeout。
    """
    from backend.services import wsl_runner

    if not _use_wsl():
        return {"success": False, "error_message": _WSL_REQUIRED_MSG, "step_id": step_id}

    work_dir_win = work_dir
    if work_dir and ("\\" in work_dir or (len(work_dir) >= 2 and work_dir[1] == ":")):
        work_dir = wsl_runner.windows_path_to_wsl(work_dir)
    ok_src, src_err = wsl_runner.verify_stack_safe_sources(work_dir_win or work_dir)
    if not ok_src:
        return {
            "success": False,
            "error_message": src_err or "Stack 源 SLC zip 在 WSL 中不可访问。",
            "step_id": step_id,
        }
    project_root = wsl_runner.get_wsl_project_root()
    if not project_root:
        return {"success": False, "error_message": "WSL 模式下请设置 INSAR_WSL_PROJECT_ROOT", "step_id": step_id}
    cmd = f"cd '{project_root}' && PYTHONPATH=\".:${{PYTHONPATH:-}}\" python3 -m backend.scripts.run_stack_wsl step --work_dir='{work_dir}' --step_id='{step_id}'"
    env_script = wsl_runner.get_wsl_env_script()
    isce_env, isce_env_err = wsl_runner.build_wsl_isce2_extra_env()
    if isce_env_err:
        return {"success": False, "error_message": isce_env_err, "step_id": step_id}
    extra = {
        "INSAR_STACK_STEP_WORK_DIR": work_dir,
        "INSAR_STACK_STEP_ID": step_id,
        "INSAR_PROJECT_ROOT": project_root,
        **isce_env,
    }
    out_line_count: List[int] = [0]

    def stream_cb(line: str) -> None:
        if progress_callback and line:
            out_line_count[0] += 1
            n = out_line_count[0]
            pct = min(5.0 + 90.0 * (1.0 - 1.0 / (1.0 + n * 0.02)), 95.0)
            progress_callback(pct, line.rstrip())

    step_timeout = _get_stack_step_timeout()
    idle_timeout = _get_stack_step_idle_timeout()
    result = wsl_runner.run_wsl(
        cmd, env_script=env_script, extra_env=extra,
        timeout=step_timeout,
        stream_callback=stream_cb,
        idle_timeout_sec=idle_timeout,
    )
    if progress_callback:
        progress_callback(100.0, "步骤完成")
    if result.get("success"):
        if result.get("idle_exit") and work_dir_win:
            _append_step_idle_note(work_dir_win, step_id, idle_timeout)
        return {"success": True, "step_id": step_id}
    return {
        "success": False,
        "error_message": result.get("error_message", "WSL 执行失败"),
        "step_id": step_id,
        "log_file": os.path.join(work_dir_win, "stack_step.log"),
    }


def _load_pipeline_state(work_dir: str) -> Dict[str, str]:
    """Load pipeline_state.json from work_dir. Returns step_id -> status (e.g. success). WSL-aware."""
    from backend.services import wsl_runner
    if _use_wsl() and (work_dir.startswith("/") or work_dir.startswith("~")):
        path = work_dir.rstrip("/") + "/" + _PIPELINE_STATE_JSON
        result = wsl_runner.run_wsl(f"cat '{path}' 2>/dev/null", timeout=5)
        if not result.get("success") or not (result.get("stdout") or "").strip():
            return {}
        try:
            data = json.loads((result.get("stdout") or "").strip())
            return data.get("steps") or {}
        except json.JSONDecodeError:
            return {}
    path = os.path.join(work_dir, _PIPELINE_STATE_JSON)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("steps") or {}
    except (OSError, json.JSONDecodeError):
        return {}


def run_stack_steps(
    work_dir: str,
    from_step_index: int,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """Run steps from from_step_index to end; skip steps already marked success in pipeline_state.json."""
    pipeline_path = os.path.join(work_dir, _PIPELINE_JSON)
    if _use_wsl() and (work_dir.startswith("/") or work_dir.startswith("~")):
        from backend.services import wsl_runner
        pipeline_path = work_dir.rstrip("/") + "/" + _PIPELINE_JSON
        result = wsl_runner.run_wsl(f"cat '{pipeline_path}'", timeout=10)
        if not result.get("success"):
            return {"success": False, "error_message": "未找到 pipeline.json"}
        try:
            pipeline = json.loads((result.get("stdout") or "").strip())
        except json.JSONDecodeError:
            return {"success": False, "error_message": "pipeline.json 解析失败"}
    else:
        if not os.path.isfile(pipeline_path):
            return {"success": False, "error_message": "未找到 pipeline.json"}
        with open(pipeline_path, "r", encoding="utf-8") as f:
            pipeline = json.load(f)
    steps = pipeline.get("steps") or []
    states = _load_pipeline_state(work_dir)
    total_pipeline = len(steps)
    to_run: List[tuple] = []
    for idx in range(from_step_index, len(steps)):
        step = steps[idx]
        step_id = step.get("id", "")
        if states.get(step_id) == "success":
            if progress_callback:
                progress_callback(0, f"步骤 {idx + 1}/{total_pipeline}: {step.get('name', step_id)}（已完成，跳过）")
            continue
        to_run.append((idx, step))
    num_to_run = len(to_run)
    if num_to_run == 0:
        if progress_callback:
            progress_callback(100.0, "全部步骤完成")
        return {"success": True}
    for i, (idx, step) in enumerate(to_run):
        step_id = step.get("id", "")
        pct = 100.0 * (i + 1) / num_to_run if num_to_run else 100.0
        if progress_callback:
            progress_callback(pct, f"步骤 {idx + 1}/{total_pipeline}: {step.get('name', step_id)}")
        out = run_stack_step(work_dir, step_id, progress_callback=progress_callback)
        if not out.get("success"):
            return out
    if progress_callback:
        progress_callback(100.0, "全部步骤完成")
    return {"success": True}


def load_pipeline(work_dir: str) -> Optional[Dict[str, Any]]:
    """Load pipeline.json from work_dir if present. When INSAR_USE_WSL=1 and work_dir is WSL path, cat via WSL."""
    from backend.services import wsl_runner
    if _use_wsl() and (work_dir.startswith("/") or work_dir.startswith("~")):
        pipeline_path = work_dir.rstrip("/") + "/" + _PIPELINE_JSON
        result = wsl_runner.run_wsl(f"cat '{pipeline_path}'", timeout=10)
        if not result.get("success"):
            return None
        stdout = (result.get("stdout") or "").strip()
        if not stdout:
            return None
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return None
    path = os.path.join(work_dir, _PIPELINE_JSON)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
