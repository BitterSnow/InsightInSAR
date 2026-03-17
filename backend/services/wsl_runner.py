"""
WSL 桥接：在 Windows 上通过 wsl 命令在 WSL 内执行 ISCE2/MintPy。
路径转换（Windows -> WSL）、发行版名称可配置、超时与实时输出。
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from typing import Callable, Dict, List, Optional

# 是否启用 WSL：环境变量 INSAR_USE_WSL=1 或 true/yes 时启用
def use_wsl() -> bool:
    v = (os.environ.get("INSAR_USE_WSL") or "").strip().lower()
    return v in ("1", "true", "yes")


def windows_path_to_wsl(windows_path: str) -> str:
    """
    将 Windows 路径转换为 WSL 可访问路径。
    例如 D:\\data\\SAFE -> /mnt/d/data/SAFE，C:\\Users -> /mnt/c/Users。
    若已是 WSL 风格（以 / 开头）或相对路径，原样返回（或规范化）。
    """
    if not windows_path or not isinstance(windows_path, str):
        return windows_path
    s = windows_path.strip().replace("\\", "/")
    # 已是 Linux 风格（以 / 开头）
    if s.startswith("/"):
        return s
    # D: or D:/path
    m = re.match(r"^([a-zA-Z])\s*:\s*(.*)$", s)
    if m:
        drive = m.group(1).lower()
        rest = (m.group(2) or "").strip().strip("/")
        return "/mnt/" + drive + ("/" + rest if rest else "")
    return s.replace("\\", "/")


def get_wsl_distro() -> Optional[str]:
    """
    返回 WSL 发行版名称。本项目中 WSL 桥接固定使用 Ubuntu（ISCE2/MintPy 环境），
    不再使用系统默认发行版（如 docker-desktop）。可通过 INSAR_WSL_DISTRO 覆盖。
    """
    v = (os.environ.get("INSAR_WSL_DISTRO") or "").strip()
    if v.lower() == "default":
        return None  # 显式写 default 时用系统默认
    return v if v else "Ubuntu"


def build_wsl_argv(
    bash_cmd: str,
    wsl_distro: Optional[str] = None,
    env_script: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    构造 wsl 命令行。bash_cmd 为要在 WSL 内执行的完整命令（可含单引号，需在调用方转义）。
    env_script: 可选，在 WSL 内 source 的脚本路径（WSL 路径）。
    extra_env: 可选，在 WSL 内 export 的变量。
    """
    parts = []
    # 先 export，再 source，这样 env 脚本内能读到 INSAR_PROJECT_ROOT 等并正确设置 PYTHONPATH
    if extra_env:
        for k, val in extra_env.items():
            safe = str(val).replace("'", "'\"'\"'")
            parts.append(f"export {k}='{safe}'")
    if env_script:
        if env_script.strip().startswith("~/"):
            suffix = env_script.strip()[2:].replace('"', '\\"')
            parts.append(f'source "$HOME/{suffix}"')
        else:
            safe = env_script.replace("'", "'\"'\"'")
            parts.append(f"source '{safe}'")
    parts.append(bash_cmd)
    inner = " && ".join(parts)
    argv = ["wsl"]
    if wsl_distro:
        argv.extend(["-d", wsl_distro])
    argv.extend(["-e", "bash", "-c", inner])
    return argv


def run_wsl(
    bash_cmd: str,
    cwd: Optional[str] = None,
    env_script: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = 3600,
    stream_callback: Optional[Callable[[str], None]] = None,
    idle_timeout_sec: Optional[int] = None,
) -> Dict[str, object]:
    """
    在 WSL 内执行 bash_cmd。cwd 应为 WSL 路径（WSL 内的工作目录），会在命令前插入 cd。
    env_script: WSL 侧环境脚本路径（如 ~/insar-wsl/env_isce2.sh）。
    extra_env: 追加的环境变量（键值对，在 WSL 内 export）。
    timeout: 秒，None 表示不限制。
    stream_callback: 若提供，每行 stdout 实时回调（stderr 合并到 stdout）。
    idle_timeout_sec: 若设置，连续无新 stdout 超过该秒数则视为步骤结束（杀进程并返回成功），用于子进程不退出但输出已停的情况。

    Returns:
        {"success": bool, "returncode": int, "stdout": str, "stderr": str, "error_message": str or None, "idle_exit": bool}
    """
    if cwd:
        # 单引号转义：' -> '"'"'
        safe_cwd = cwd.replace("'", "'\"'\"'")
        bash_cmd = f"cd '{safe_cwd}' && {bash_cmd}"
    wsl_distro = get_wsl_distro()
    argv = build_wsl_argv(bash_cmd, wsl_distro=wsl_distro, env_script=env_script, extra_env=extra_env)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        if stream_callback:
            kwargs = dict(
                cwd=None,  # cwd 在 Windows 上无法直接设为 WSL 路径，需在 bash_cmd 内 cd
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            # 打包为 exe 在 Windows 上运行时，默认隐藏 wsl.exe 控制台窗口
            if hasattr(subprocess, "CREATE_NO_WINDOW") and os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(argv, **kwargs)
            lines: List[str] = []
            last_output_time: List[float] = [time.monotonic()]

            def read_out():
                if proc.stdout:
                    for line in iter(proc.stdout.readline, ""):
                        lines.append(line)
                        last_output_time[0] = time.monotonic()
                        stream_callback(line)
            t = threading.Thread(target=read_out, daemon=True)
            t.start()
            # 结束条件：1) 进程退出 2) 可选 timeout 3) 可选 idle：连续无新输出超过 idle_timeout_sec 视为结束（数据已出完、进程不退出时用）
            poll_interval = 0.25
            deadline = (time.monotonic() + timeout) if timeout is not None else None
            idle_exit = False
            try:
                while proc.poll() is None:
                    if deadline is not None and time.monotonic() >= deadline:
                        proc.kill()
                        proc.wait()
                        t.join(timeout=2)
                        return {
                            "success": False,
                            "returncode": -1,
                            "stdout": "".join(lines),
                            "stderr": "",
                            "error_message": "命令超时",
                            "idle_exit": False,
                        }
                    if idle_timeout_sec is not None and (time.monotonic() - last_output_time[0]) >= idle_timeout_sec:
                        idle_exit = True
                        proc.kill()
                        proc.wait()
                        t.join(timeout=2)
                        break
                    time.sleep(poll_interval)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise
            t.join(timeout=5)
            out = "".join(lines)
            if idle_exit:
                return {
                    "success": True,
                    "returncode": 0,
                    "stdout": out,
                    "stderr": "",
                    "error_message": None,
                    "idle_exit": True,
                }
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode or 0,
                "stdout": out,
                "stderr": "",
                "error_message": None if proc.returncode == 0 else (out.strip() or "命令返回非零"),
                "idle_exit": False,
            }
        else:
            # 若需 cwd，必须在 bash_cmd 里包含 cd
            kwargs_run = dict(
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            if hasattr(subprocess, "CREATE_NO_WINDOW") and os.name == "nt":
                kwargs_run["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(argv, **kwargs_run)
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "error_message": None if result.returncode == 0 else ((result.stderr or result.stdout or "").strip() or "命令返回非零"),
            }
    except FileNotFoundError as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": f"无法启动 WSL: {e}",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": "命令超时",
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": str(e),
        }


def _get_wsl_default_env_script() -> Optional[str]:
    """当未设置 INSAR_WSL_ENV_SCRIPT 时，尝试解析 WSL 内 ~/insar-wsl/env_isce2.sh 是否存在并返回其绝对路径。"""
    try:
        argv = ["wsl"]
        if get_wsl_distro():
            argv.extend(["-d", get_wsl_distro()])
        argv.extend([
            "-e", "bash", "-c",
            '[ -f "$HOME/insar-wsl/env_isce2.sh" ] && echo "$HOME/insar-wsl/env_isce2.sh"',
        ])
        r = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        path = (r.stdout or "").strip()
        return path if path else None
    except Exception:
        return None


def get_wsl_env_script() -> Optional[str]:
    """从环境变量读取 WSL 侧环境脚本路径（WSL 路径）；未设置时尝试默认 ~/insar-wsl/env_isce2.sh。"""
    v = (os.environ.get("INSAR_WSL_ENV_SCRIPT") or "").strip()
    if v:
        return v
    return _get_wsl_default_env_script()


def _resolve_windows_project_root_to_wsl() -> Optional[str]:
    """用 wslpath 将 INSAR_PROJECT_ROOT（Windows 路径）转为 WSL 路径；失败返回 None。"""
    win_root = (os.environ.get("INSAR_PROJECT_ROOT") or "").strip()
    if not win_root:
        return None
    win_path = win_root.replace("\\", "/").strip()
    wsl_distro = get_wsl_distro()
    argv = ["wsl"]
    if wsl_distro:
        argv.extend(["-d", wsl_distro])
    argv.extend(["-e", "wslpath", "-a", win_path])
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            return (r.stdout or "").strip()
    except Exception:
        pass
    return None


def get_wsl_project_root() -> Optional[str]:
    """
    返回 WSL 侧项目代码根路径（用于 cd 和 dem.py 等）。
    优先用 INSAR_WSL_PROJECT_ROOT；未设置时用 wslpath 将 INSAR_PROJECT_ROOT（Windows）转为 WSL 路径。
    """
    wsl_root = (os.environ.get("INSAR_WSL_PROJECT_ROOT") or "").strip()
    if wsl_root:
        return wsl_root
    return _resolve_windows_project_root_to_wsl()


def check_wsl_project_root() -> Dict[str, object]:
    """
    检查 WSL 项目根是否正确：是否已设置、在 WSL 内是否存在、是否包含 lib/MintPy-main/src。
    返回 {"ok": bool, "message": str, "path": str|None, "mintpy_src_exists": bool|None}
    """
    root = get_wsl_project_root()
    if not root:
        return {
            "ok": False,
            "message": "INSAR_WSL_PROJECT_ROOT 未设置。请用 scripts/start_desktop_wsl.bat 启动 Desktop，或设置环境变量 INSAR_WSL_PROJECT_ROOT（WSL 路径，如 /mnt/d/coding/insar-system 或 ~/insar-system）。",
            "path": None,
            "mintpy_src_exists": None,
        }
    wsl_distro = get_wsl_distro()
    argv = ["wsl"]
    if wsl_distro:
        argv.extend(["-d", wsl_distro])
    # 在 WSL 内检查目录存在且包含 lib/MintPy-main/src；root 可能含 ~ 需展开
    safe_root = root.replace("'", "'\"'\"'")
    bash_cmd = f"ROOT=\"$(eval echo {safe_root})\"; [ -d \"$ROOT\" ] && [ -d \"$ROOT/lib/MintPy-main/src\" ] && echo OK || echo FAIL"
    argv.extend(["-e", "bash", "-c", bash_cmd])
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if r.returncode != 0 or out != "OK":
            return {
                "ok": False,
                "message": f"WSL 内路径不存在或缺少 lib/MintPy-main/src：{root}",
                "path": root,
                "mintpy_src_exists": False,
            }
        return {
            "ok": True,
            "message": f"WSL 项目根正确：{root}",
            "path": root,
            "mintpy_src_exists": True,
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "message": "未找到 wsl 命令，请确认已安装 WSL。",
            "path": root,
            "mintpy_src_exists": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "message": "WSL 检查超时。",
            "path": root,
            "mintpy_src_exists": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
            "path": root,
            "mintpy_src_exists": None,
        }


def get_wsl_workspace_root() -> str:
    """从环境变量读取 WSL 侧项目工作区根路径（如 ~/insar-projects），未设置时返回默认。"""
    v = (os.environ.get("INSAR_WSL_WORKSPACE_ROOT") or "").strip()
    return v or "~/insar-projects"
