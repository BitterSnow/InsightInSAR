"""
WSL 内执行的 Stack 入口：stack_init（stackSentinel + 解析 pipeline 并输出 JSON）与 run_step（按 step_id 执行）。
供 Windows 侧通过 wsl_runner 调用；所有路径均为 WSL 路径。
用法:
  python -m backend.scripts.run_stack_wsl init --work_dir=... --slc_dir=... (其他 stackSentinel 参数)
  python -m backend.scripts.run_stack_wsl step --work_dir=... --step_id=run_01_...
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import threading
from datetime import datetime


def _project_root() -> str:
    root = os.environ.get("INSAR_PROJECT_ROOT", "")
    if root:
        return root
    # 假定在 insar-system 仓库内
    this_dir = os.path.abspath(os.path.dirname(__file__))
    return os.path.abspath(os.path.join(this_dir, "..", "..", ".."))


def _apply_tops_stack_runtime_env(env: dict, tops_stack_dir: str) -> None:
    """PATH 指向 topsStack 脚本目录；PYTHONPATH 指向其父目录以便 import topsStack。"""
    tops_stack_dir = tops_stack_dir.rstrip("/")
    stack_pp = (os.environ.get("INSAR_ISCE2_STACK_PYTHONPATH") or "").strip()
    if not stack_pp:
        try:
            from backend.services.wsl_runner import get_tops_stack_pythonpath

            stack_pp = get_tops_stack_pythonpath(tops_stack_dir)
        except Exception:
            base = tops_stack_dir
            if os.path.basename(base) == "topsStack":
                stack_pp = os.path.dirname(base)
            else:
                stack_pp = base
    if stack_pp:
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = stack_pp + (os.pathsep + existing if existing else "")
    path_sep = os.pathsep
    env["PATH"] = tops_stack_dir + path_sep + env.get("PATH", "")


def _tops_stack(root: str) -> str:
    """
    topsStack 目录（含 stackSentinel.py、fetchOrbit.py）。
    优先 INSAR_ISCE2_TOPS_STACK / WSL conda $CONDA_PREFIX/share/isce2/topsStack，不用 /mnt 下 Windows 源码。
    """
    try:
        from backend.services.wsl_runner import get_tops_stack_dir_for_root

        found = get_tops_stack_dir_for_root(root)
        if found:
            return found.rstrip("/")
    except Exception:
        pass
    for key in ("INSAR_ISCE2_TOPS_STACK", "INSAR_WSL_ISCE2_TOPS_STACK"):
        alt = (os.environ.get(key) or "").strip().rstrip("/")
        if alt and os.path.isfile(os.path.join(alt, "stackSentinel.py")):
            return alt
    prefix = (os.environ.get("CONDA_PREFIX") or "").strip().rstrip("/")
    if prefix:
        conda_tops = os.path.join(prefix, "share", "isce2", "topsStack")
        if os.path.isfile(os.path.join(conda_tops, "stackSentinel.py")):
            return conda_tops
    return ""


# 与 stack_processing_service 同步；WSL 内不导入该模块以免依赖 pydantic
_STACK_STEP_NAMES = {
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


def _parse_run_files_to_pipeline(work_dir: str) -> dict | None:
    """解析 work_dir/run_files 为 pipeline 字典，仅用 stdlib，不依赖 backend/shared_models。"""
    run_dir = os.path.join(work_dir, "run_files")
    if not os.path.isdir(run_dir):
        return None
    run_files = sorted(
        n for n in os.listdir(run_dir)
        if n.startswith("run_") and not os.path.isdir(os.path.join(run_dir, n))
    )
    steps = []
    for rname in run_files:
        path = os.path.join(run_dir, rname)
        commands = []
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    commands.append(line)
        name = _STACK_STEP_NAMES.get(rname, rname)
        steps.append({"id": rname, "name": name, "commands": commands})
    return {"work_dir": work_dir, "steps": steps}


def cmd_init(args: argparse.Namespace) -> int:
    # 支持从环境变量 INSAR_STACK_INIT_JSON 读取 JSON（避免 shell 转义）
    if os.environ.get("INSAR_STACK_INIT_JSON"):
        try:
            data = json.loads(os.environ["INSAR_STACK_INIT_JSON"])
            work_dir = data["work_dir"]
            slc_dir = data["slc_dir"]
            orbit_dir = data["orbit_dir"]
            dem_path = data["dem_path"]
            aux_dir = data["aux_dir"]
            args.polarization = data.get("polarization", "vv")
            args.workflow = data.get("workflow", "sequential")
            args.swaths = data.get("swaths", "1 2 3")
            args.coregistration = data.get("coregistration", "NESD")
            args.num_connections = int(data.get("num_connections", 2))
            args.num_process = int(data.get("num_process", 4))
            args.bbox = data.get("bbox", "")
            args.reference_date = data.get("reference_date", "")
            args.exclude_dates = data.get("exclude_dates", "")
            args.include_dates = data.get("include_dates", "")
            args.start_date = data.get("start_date", "")
            args.stop_date = data.get("stop_date", "")
        except Exception as e:
            print(json.dumps({"success": False, "error": str(e)}), file=sys.stderr)
            return 1
    else:
        work_dir = args.work_dir or ""
        slc_dir = args.slc_dir or ""
        orbit_dir = args.orbit_dir or ""
        dem_path = args.dem_path or ""
        aux_dir = args.aux_dir or ""
        if not all([work_dir, slc_dir, orbit_dir, dem_path, aux_dir]):
            print("INSAR_STACK_INIT_JSON not set and required --work_dir, --slc_dir, --orbit_dir, --dem_path, --aux_dir missing", file=sys.stderr)
            return 1
    root = _project_root()
    tops_stack_dir = _tops_stack(root)
    if not tops_stack_dir:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": (
                        "未找到 topsStack（stackSentinel.py）。"
                        "请在 WSL Ubuntu conda 环境 isce2 中安装 ISCE2，"
                        "或设置 INSAR_ISCE2_TOPS_STACK=$CONDA_PREFIX/share/isce2/topsStack。"
                    ),
                }
            ),
            file=sys.stderr,
        )
        return 1
    stack_sentinel = os.path.join(tops_stack_dir, "stackSentinel.py")
    if not os.path.isfile(stack_sentinel):
        print(json.dumps({"success": False, "error": f"stackSentinel.py not found: {stack_sentinel}"}), file=sys.stderr)
        return 1
    os.makedirs(work_dir, exist_ok=True)
    env = os.environ.copy()
    _apply_tops_stack_runtime_env(env, tops_stack_dir)
    argv = [
        sys.executable,
        stack_sentinel,
        "-s", slc_dir,
        "-o", orbit_dir,
        "-a", aux_dir,
        "-w", work_dir,
        "-d", dem_path,
        "-p", args.polarization,
        "-W", args.workflow,
        "-n", args.swaths,
        "-C", args.coregistration,
        "-c", str(args.num_connections),
        "--num_proc", str(args.num_process),
    ]
    if args.bbox:
        argv.extend(["-b", args.bbox])
    if args.reference_date:
        argv.extend(["-m", args.reference_date])
    if args.exclude_dates:
        argv.extend(["-x", args.exclude_dates])
    if args.include_dates:
        argv.extend(["-i", args.include_dates])
    if args.start_date:
        argv.extend(["--start_date", args.start_date])
    if args.stop_date:
        argv.extend(["--stop_date", args.stop_date])
    try:
        r = subprocess.run(argv, cwd=work_dir, env=env, timeout=3600, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print(json.dumps({"success": False, "error": "stackSentinel 运行超时"}), file=sys.stderr)
        return 1
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        print(json.dumps({"success": False, "error": err or f"exit {r.returncode}"}), file=sys.stderr)
        return 1
    # 解析 run_files -> pipeline，输出 JSON 到 stdout（供 Windows 解析）；本地解析避免依赖 pydantic
    pipeline = _parse_run_files_to_pipeline(work_dir)
    if not pipeline:
        print(json.dumps({"success": False, "error": "解析 run_files 失败"}), file=sys.stderr)
        return 1
    pipeline_path = os.path.join(work_dir, "pipeline.json")
    with open(pipeline_path, "w", encoding="utf-8") as f:
        json.dump(pipeline, f, ensure_ascii=False, indent=2)
    print(json.dumps({"success": True, "pipeline": pipeline}))
    return 0


def _resolve_topsstack_script(script_token: str, tops_stack_dir: str, work_dir: str) -> str:
    """run_files 中的 extractCommonValidRegion.py 等脚本名 -> topsStack 目录下绝对路径。"""
    name = os.path.basename(script_token)
    candidate = os.path.join(tops_stack_dir, name)
    if os.path.isfile(candidate):
        return candidate
    alt = os.path.join(work_dir, name)
    if os.path.isfile(alt):
        return alt
    return candidate


def _argv_from_run_line(line: str, work_dir: str, tops_stack_dir: str, wrapper_py: str) -> list | None:
    """
    将 run_files 中的一行命令转为 argv。
    支持 SentinelWrapper.py -c <config> 与 topsStack 直调脚本（如 extractCommonValidRegion.py）。
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split()
    if "SentinelWrapper" in line:
        config_path = None
        for j, p in enumerate(parts):
            if p == "-c" and j + 1 < len(parts):
                config_path = parts[j + 1]
                break
        if not config_path:
            return None
        if not os.path.isabs(config_path):
            config_path = os.path.join(work_dir, config_path)
        return [sys.executable, wrapper_py, "-c", config_path]
    if parts[0].endswith(".py"):
        script_path = _resolve_topsstack_script(parts[0], tops_stack_dir, work_dir)
        return [sys.executable, script_path, *parts[1:]]
    return None


def _run_subprocess_argv(
    argv: list,
    *,
    cwd: str,
    env: dict,
    step_log_path: str,
    step_id: str,
    timeout_sec: int | None,
) -> int:
    """执行单条子命令；返回进程退出码。"""
    start_iso = datetime.utcnow().isoformat() + "Z"
    proc = subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out_lines: list[str] = []

    def read_and_forward() -> None:
        if proc.stdout:
            for out_line in iter(proc.stdout.readline, ""):
                out_lines.append(out_line)
                sys.stdout.write(out_line)
                sys.stdout.flush()

    reader = threading.Thread(target=read_and_forward, daemon=True)
    reader.start()
    try:
        if timeout_sec is not None:
            proc.wait(timeout=timeout_sec)
        else:
            proc.wait()
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        reader.join(timeout=2)
        stdout_str = "".join(out_lines)
        _append_step_log(
            step_log_path,
            step_id,
            argv,
            -1,
            stdout_str,
            "\nTimeoutExpired",
            start_iso,
            datetime.utcnow().isoformat() + "Z",
        )
        return -1
    reader.join(timeout=5)
    stdout_str = "".join(out_lines)
    returncode = proc.returncode if proc.returncode is not None else -1
    _append_step_log(
        step_log_path,
        step_id,
        argv,
        returncode,
        stdout_str,
        "",
        start_iso,
        datetime.utcnow().isoformat() + "Z",
    )
    return returncode


def _append_step_log(
    log_path: str,
    step_id: str,
    argv: list,
    returncode: int,
    stdout: str,
    stderr: str,
    start_iso: str,
    end_iso: str,
) -> None:
    """追加单步执行关键信息到 stack_step.log（与 backend 侧格式兼容）。"""
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write("\n" + "=" * 60 + "\n")
            f.write(f"[{step_id}] start: {start_iso}  end: {end_iso}\n")
            f.write("Command: " + " ".join(argv) + "\n")
            f.write(f"Return code: {returncode}\n")
            out = (stdout or "").strip()
            err = (stderr or "").strip()
            if out:
                f.write("--- stdout (last 200 lines) ---\n")
                lines = out.splitlines()
                for ln in lines[-200:]:
                    f.write(ln + "\n")
            if err:
                f.write("--- stderr ---\n")
                f.write(err[:8000] + ("..." if len(err) > 8000 else "") + "\n")
    except OSError:
        pass


def cmd_step(args: argparse.Namespace) -> int:
    if os.environ.get("INSAR_STACK_STEP_WORK_DIR"):
        work_dir = os.environ["INSAR_STACK_STEP_WORK_DIR"]
        step_id = os.environ.get("INSAR_STACK_STEP_ID", args.step_id)
    else:
        work_dir = args.work_dir
        step_id = args.step_id
    pipeline_path = os.path.join(work_dir, "pipeline.json")
    if not os.path.isfile(pipeline_path):
        print(f"未找到 pipeline.json: {pipeline_path}", file=sys.stderr)
        os._exit(1)
    with open(pipeline_path, "r", encoding="utf-8") as f:
        pipeline = json.load(f)
    steps = pipeline.get("steps") or []
    step = next((s for s in steps if s.get("id") == step_id), None)
    if not step:
        print(f"未找到步骤: {step_id}", file=sys.stderr)
        os._exit(1)
    root = _project_root()
    wrapper_py = os.path.join(_tops_stack(root), "SentinelWrapper.py")
    if not os.path.isfile(wrapper_py):
        print(f"SentinelWrapper.py not found: {wrapper_py}", file=sys.stderr)
        os._exit(1)
    step_log_path = os.path.join(work_dir, "stack_step.log")
    timeout_sec = None
    try:
        t = os.environ.get("INSAR_STACK_STEP_TIMEOUT", "").strip()
        if t:
            timeout_sec = max(60, int(t))
    except ValueError:
        pass
    tops_stack_dir = _tops_stack(root)
    step_env = os.environ.copy()
    _apply_tops_stack_runtime_env(step_env, tops_stack_dir)
    raw_commands = [ln.strip() for ln in (step.get("commands") or []) if ln.strip()]
    ran_count = 0
    for line in raw_commands:
        argv = _argv_from_run_line(line, work_dir, tops_stack_dir, wrapper_py)
        if not argv:
            print(f"跳过无法解析的命令行: {line}", file=sys.stderr)
            continue
        ran_count += 1
        rc = _run_subprocess_argv(
            argv,
            cwd=work_dir,
            env=step_env,
            step_log_path=step_log_path,
            step_id=step_id,
            timeout_sec=timeout_sec,
        )
        if rc != 0:
            os._exit(rc)
    if ran_count == 0 and raw_commands:
        print(
            json.dumps(
                {
                    "success": False,
                    "error": f"步骤 {step_id} 无已执行命令（可能仅含未支持的 run_files 行）",
                }
            ),
            file=sys.stderr,
        )
        os._exit(1)
    if "extract_stack_valid_region" in step_id:
        stack_meta_dir = os.path.join(work_dir, "stack")
        iw_xml = glob.glob(os.path.join(stack_meta_dir, "IW*.xml"))
        if not iw_xml:
            print(
                json.dumps(
                    {
                        "success": False,
                        "error": (
                            f"步骤 {step_id} 未在 {stack_meta_dir} 下生成 IW*.xml；"
                            "第 7 步 merge 需要该目录（工作区为 .../stack 时路径为 .../stack/stack/，属 ISCE 约定）。"
                        ),
                    }
                ),
                file=sys.stderr,
            )
            os._exit(1)
    os._exit(0)


def main() -> int:
    parser = argparse.ArgumentParser(description="WSL Stack init/step runner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    # init (args optional when INSAR_STACK_INIT_JSON is set)
    p_init = sub.add_parser("init")
    p_init.add_argument("--work_dir", default="")
    p_init.add_argument("--slc_dir", default="")
    p_init.add_argument("--orbit_dir", default="")
    p_init.add_argument("--dem_path", default="")
    p_init.add_argument("--aux_dir", default="")
    p_init.add_argument("--polarization", default="vv")
    p_init.add_argument("--workflow", default="sequential")
    p_init.add_argument("--swaths", default="1 2 3")
    p_init.add_argument("--coregistration", default="NESD")
    p_init.add_argument("--num_connections", type=int, default=2)
    p_init.add_argument("--num_process", type=int, default=4)
    p_init.add_argument("--bbox", default="")
    p_init.add_argument("--reference_date", default="")
    p_init.add_argument("--exclude_dates", default="")
    p_init.add_argument("--include_dates", default="")
    p_init.add_argument("--start_date", default="")
    p_init.add_argument("--stop_date", default="")
    # step
    p_step = sub.add_parser("step")
    p_step.add_argument("--work_dir", required=True)
    p_step.add_argument("--step_id", required=True)
    args = parser.parse_args()
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "step":
        return cmd_step(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
