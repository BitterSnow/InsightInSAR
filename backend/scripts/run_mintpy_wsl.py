"""
WSL 内执行的 MintPy 单步入口：与 Stack run_stack_wsl step 一致，在步骤脚本内用 Popen 跑 mintpy，
实时转发 stdout、写 mintpy_step.log，最后 os._exit(returncode) 确保结束信号被及时捕获。
供 Windows 侧通过 wsl_runner 调用；work_dir 为 WSL 路径。
用法:
  python -m backend.scripts.run_mintpy_wsl step --work_dir=<wsl_path> --step_id=<step_id>
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
from datetime import datetime

_TEMPLATE_DEFAULT = "smallbaselineApp.cfg"


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
    """追加单步执行信息到 mintpy_step.log（与 backend _append_mintpy_log 格式兼容）。"""
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
    work_dir = os.environ.get("INSAR_MINTPY_STEP_WORK_DIR", "").strip() or args.work_dir
    step_id = os.environ.get("INSAR_MINTPY_STEP_ID", "").strip() or args.step_id
    if not work_dir or not step_id:
        print("run_mintpy_wsl step: need --work_dir and --step_id (or env)", file=sys.stderr)
        os._exit(1)
    work_dir = work_dir.rstrip("/")
    cfg_path = os.path.join(work_dir, _TEMPLATE_DEFAULT)
    if not os.path.isfile(cfg_path):
        print(f"未找到 {_TEMPLATE_DEFAULT}: {cfg_path}", file=sys.stderr)
        os._exit(1)
    argv = [
        sys.executable,
        "-m",
        "mintpy",
        "smallbaselineApp",
        _TEMPLATE_DEFAULT,
        "--dir",
        ".",
        "--dostep",
        step_id,
    ]
    log_path = os.path.join(work_dir, "mintpy_step.log")
    start_iso = datetime.utcnow().isoformat() + "Z"
    proc = subprocess.Popen(
        argv,
        cwd=work_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out_lines: list[str] = []

    def read_and_forward() -> None:
        if proc.stdout is None:
            return
        for line in iter(proc.stdout.readline, ""):
            out_lines.append(line)
            sys.stdout.write(line)
            sys.stdout.flush()

    reader = threading.Thread(target=read_and_forward, daemon=True)
    reader.start()
    timeout_sec = None
    try:
        t = os.environ.get("INSAR_MINTPY_STEP_TIMEOUT", "").strip()
        if t:
            timeout_sec = max(60, int(t))
    except ValueError:
        pass
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
        end_iso = datetime.utcnow().isoformat() + "Z"
        _append_step_log(
            log_path, step_id, argv, -1,
            stdout_str, "\nTimeoutExpired",
            start_iso, end_iso,
        )
        print(f"步骤 {step_id} 超时", file=sys.stderr)
        os._exit(1)
    reader.join(timeout=5)
    stdout_str = "".join(out_lines)
    returncode = proc.returncode if proc.returncode is not None else 0
    end_iso = datetime.utcnow().isoformat() + "Z"
    _append_step_log(log_path, step_id, argv, returncode, stdout_str, "", start_iso, end_iso)
    # 与 Stack 一致：步骤脚本内显式退出，确保父进程能及时捕获结束
    os._exit(returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="WSL MintPy step runner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_step = sub.add_parser("step")
    p_step.add_argument("--work_dir", default="")
    p_step.add_argument("--step_id", default="")
    args = parser.parse_args()
    if args.cmd == "step":
        cmd_step(args)
        return 0  # unreachable (os._exit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
