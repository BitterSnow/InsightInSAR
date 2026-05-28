"""
WSL 桥接：在 Windows 上通过 wsl 命令在 WSL 内执行 ISCE2/MintPy。
路径转换（Windows -> WSL）、发行版名称可配置、超时与实时输出。
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time
import sys
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Windows 上优先使用 System32 下 wsl.exe 的完整路径，避免 PATH 受限或策略拦截导致权限错误
def _wsl_executable() -> str:
    if os.name != "nt":
        return "wsl"
    sysroot = os.environ.get("SystemRoot", "C:\\Windows")
    full = os.path.join(sysroot, "System32", "wsl.exe")
    if os.path.isfile(full):
        return full
    return "wsl.exe"

# 是否启用 WSL：环境变量 INSAR_USE_WSL=1 或 true/yes 时启用；未设置但在应用内（INSAR_PROJECT_ROOT 已设）时也视为启用
def use_wsl() -> bool:
    v = (os.environ.get("INSAR_USE_WSL") or "").strip().lower()
    if v in ("1", "true", "yes"):
        return True
    if v in ("0", "false", "no"):
        return False
    # 未显式设置：若在 InSAR 应用上下文（由 start_desktop_wsl.bat 或 desktop.main 设置），默认启用 WSL
    if os.environ.get("INSAR_PROJECT_ROOT"):
        return True
    return False


def windows_path_to_wsl(windows_path: str) -> str:
    """
    将 Windows 路径转换为 WSL 可访问路径（启发式 /mnt/<盘符>/...）。
    网络盘或未挂载盘符可能不可用；请优先使用 resolve_windows_path_to_wsl()。
    """
    if not windows_path or not isinstance(windows_path, str):
        return windows_path
    s = windows_path.strip().replace("\\", "/")
    if s.startswith("/"):
        return s
    m = re.match(r"^([a-zA-Z])\s*:\s*(.*)$", s)
    if m:
        drive = m.group(1).lower()
        rest = (m.group(2) or "").strip().strip("/")
        return "/mnt/" + drive + ("/" + rest if rest else "")
    return s.replace("\\", "/")


def _wslpath_absolute(windows_path: str) -> Optional[str]:
    """调用 WSL wslpath -a 将 Windows 路径转为 WSL 绝对路径；失败返回 None。"""
    if os.name != "nt":
        return None
    win_path = windows_path.strip().replace("\\", "/")
    if not win_path or win_path.startswith("/"):
        return None
    load_wsl_config_env()
    wsl_distro = get_wsl_distro()
    argv = [_wsl_executable()]
    if wsl_distro:
        argv.extend(["-d", wsl_distro])
    argv.extend(["-e", "wslpath", "-a", win_path])
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode == 0 and (r.stdout or "").strip():
            return (r.stdout or "").strip()
    except Exception:
        pass
    return None


def _wsl_test_dir_exists(wsl_path: str) -> bool:
    safe = wsl_path.replace("'", "'\"'\"'")
    bash_cmd = f"test -d '{safe}'"
    argv = [_wsl_executable()]
    distro = get_wsl_distro()
    if distro:
        argv.extend(["-d", distro])
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
        return r.returncode == 0
    except Exception:
        return False


def _wsl_is_drvfs_mounted(mount_point: str) -> bool:
    """/mnt/k 等目录可能存在但未 drvfs 挂载（空目录）；用 findmnt 判断。"""
    safe = mount_point.replace("'", "'\"'\"'")
    bash_cmd = (
        f"findmnt -n -o FSTYPE '{safe}' 2>/dev/null | grep -qi drvfs"
    )
    argv = [_wsl_executable()]
    distro = get_wsl_distro()
    if distro:
        argv.extend(["-d", distro])
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
        return r.returncode == 0
    except Exception:
        return False


def collect_drive_letters_from_paths(*paths: str) -> set[str]:
    """从 Windows 或 WSL 路径提取盘符（小写）。"""
    letters: set[str] = set()
    for raw in paths:
        if not raw:
            continue
        p = str(raw).strip()
        m = re.match(r"^([a-zA-Z])\s*:", p.replace("/", "\\"))
        if m:
            letters.add(m.group(1).lower())
            continue
        m2 = re.match(r"^/mnt/([a-zA-Z])(?:/|$)", p.replace("\\", "/"))
        if m2:
            letters.add(m2.group(1).lower())
    return letters


def ensure_drives_for_paths(*paths: str) -> None:
    """确保路径涉及的 Windows 盘符在 WSL 内已 drvfs 挂载。"""
    load_wsl_config_env()
    for letter in sorted(collect_drive_letters_from_paths(*paths)):
        ensure_drvfs_drive_mounted(letter)


def verify_stack_safe_sources(work_dir: str) -> tuple[bool, Optional[str]]:
    """
    读取 work_dir/SAFE_files.txt，挂载对应盘符并检查各 zip 在 WSL 内可读。
    work_dir 可为 Windows 或 WSL 路径。
    """
    load_wsl_config_env()
    win_dir = work_dir
    if work_dir.startswith("/mnt/") or work_dir.startswith("~"):
        win_dir = wsl_path_to_windows(work_dir.rstrip("/"))
    safe_list = os.path.join(win_dir, "SAFE_files.txt")
    if not os.path.isfile(safe_list):
        return True, None
    missing: List[str] = []
    wsl_paths: List[str] = []
    try:
        with open(safe_list, encoding="utf-8", errors="replace") as f:
            for line in f:
                wsl_p = line.strip()
                if not wsl_p or wsl_p.startswith("#"):
                    continue
                wsl_paths.append(wsl_p)
    except OSError as exc:
        return False, f"无法读取 SAFE_files.txt: {exc}"
    ensure_drives_for_paths(*wsl_paths)
    for wsl_p in wsl_paths:
        if not _wsl_test_file_exists(wsl_p):
            missing.append(wsl_p)
    if not missing:
        return True, None
    letters = sorted(collect_drive_letters_from_paths(*missing))
    mount_hint = ""
    if letters:
        mount_hint = (
            "\n请在 Ubuntu 终端执行（将盘符换成实际值）：\n"
            + "\n".join(
                f"  sudo mkdir -p /mnt/{L} && sudo mount -t drvfs {L.upper()}: /mnt/{L}"
                for L in letters
            )
        )
    sample = missing[0]
    return False, (
        f"Stack 仍依赖原始 SLC zip（.slc.vrt → vsizip），但 WSL 内无法访问 {len(missing)} 个源文件。\n"
        f"示例：{sample}\n"
        "请确认 Windows 下该 zip 存在，且对应盘符已在 WSL 挂载。"
        + mount_hint
    )


def _wsl_mounted_drive_letters() -> List[str]:
    """返回 WSL /mnt 下已 drvfs 挂载的盘符（小写）列表。"""
    argv = [_wsl_executable()]
    distro = get_wsl_distro()
    if distro:
        argv.extend(["-d", distro])
    argv.extend(["-e", "bash", "-c", "ls -1 /mnt 2>/dev/null || true"])
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode != 0:
            return []
        letters = [
            ln.strip().lower()
            for ln in (r.stdout or "").splitlines()
            if len(ln.strip()) == 1 and ln.strip().isalpha()
        ]
        return [L for L in letters if _wsl_is_drvfs_mounted(f"/mnt/{L}")]
    except Exception:
        return []


def resolve_windows_path_to_wsl(windows_path: str) -> tuple[Optional[str], Optional[str]]:
    """
    将 Windows 路径解析为当前 INSAR_WSL_DISTRO 内可访问的 WSL 路径，并验证目录存在。
    返回 (wsl_path, error_message)。
    """
    if not windows_path or not str(windows_path).strip():
        return None, "路径为空。"
    raw = str(windows_path).strip()
    if not os.path.isdir(raw):
        return None, f"Windows 下目录不存在或不可访问：{raw}"

    load_wsl_config_env()
    distro = get_wsl_distro() or "Ubuntu"

    m_drive = re.match(r"^([a-zA-Z])\s*:", raw.replace("/", "\\"))
    if m_drive:
        ensure_drvfs_drive_mounted(m_drive.group(1))

    wsl_path = _wslpath_absolute(raw)
    if not wsl_path:
        wsl_path = windows_path_to_wsl(raw)

    if _wsl_test_dir_exists(wsl_path):
        return wsl_path, None

    drive_hint = ""
    if m_drive:
        letter = m_drive.group(1).lower()
        mounted = _wsl_mounted_drive_letters()
        if letter not in mounted:
            mounted_str = ", ".join(f"{x}:" for x in mounted) if mounted else "（无）"
            drive_hint = (
                f"\n盘符 {m_drive.group(1).upper()}: 在 WSL「{distro}」的 /mnt 下仍不可访问；"
                f"当前可见：{mounted_str}。"
            )

    return None, (
        f"WSL 发行版「{distro}」无法访问该目录。\n"
        f"Windows 路径：{raw}\n"
        f"WSL 路径：{wsl_path}\n"
        f"{drive_hint}\n"
        "可在 Ubuntu 终端执行：sudo mount -t drvfs N: /mnt/n（将 N 换成对应盘符），"
        "或检查 Windows 下该路径是否可访问。"
    )


def wsl_path_to_windows(wsl_path: str) -> str:
    """
    Convert a WSL path like /mnt/d/foo/bar to a Windows path like D:\\foo\\bar.
    If input is not a /mnt/<drive>/ path, return as-is.
    """
    if not wsl_path or not isinstance(wsl_path, str):
        return wsl_path
    s = wsl_path.strip().replace("\\", "/")
    m = re.match(r"^/mnt/([a-zA-Z])/(.*)$", s)
    if not m:
        return wsl_path
    drive = m.group(1).upper()
    rest = m.group(2).replace("/", "\\")
    return f"{drive}:\\{rest}" if rest else f"{drive}:\\"


_wsl_config_env_loaded = False


def load_wsl_config_env(project_root: Optional[str] = None) -> None:
    """
    从 wsl_config.env 加载 INSAR_WSL_*（setdefault，不覆盖已设环境变量）。
    与 desktop.main._load_wsl_config 查找路径一致。
    """
    global _wsl_config_env_loaded
    if _wsl_config_env_loaded:
        return
    _wsl_config_env_loaded = True
    candidates: List[str] = []
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or ""
    if local:
        candidates.append(os.path.join(local, "InSAR", "wsl_config.env"))
    root = (project_root or os.environ.get("INSAR_PROJECT_ROOT") or "").strip()
    if root:
        candidates.append(os.path.join(root, "wsl_config.env"))
    for cfg in candidates:
        if not os.path.isfile(cfg):
            continue
        try:
            with open(cfg, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k:
                        os.environ.setdefault(k, v)
            logger.info("已加载 WSL 配置: %s", cfg)
            return
        except OSError as exc:
            logger.debug("读取 WSL 配置失败 %s: %s", cfg, exc)


def list_wsl_distros() -> List[str]:
    """列出本机已安装的 WSL 发行版名称。"""
    try:
        r = subprocess.run(
            [_wsl_executable(), "-l", "-q"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
        text = (r.stdout or r.stderr or "").replace("\x00", "")
        return [ln.strip() for ln in text.splitlines() if ln.strip()]
    except Exception:
        return []


def get_wsl_distro() -> Optional[str]:
    """
    返回 WSL 发行版名称。优先 INSAR_WSL_DISTRO（含 wsl_config.env）；
    未配置时默认 Ubuntu（与本项目 Stack/DEM 约定一致）。
    """
    load_wsl_config_env()
    v = (os.environ.get("INSAR_WSL_DISTRO") or "").strip()
    if v.lower() == "default":
        return None
    if v:
        return v
    installed = {d.lower(): d for d in list_wsl_distros()}
    if "ubuntu" in installed:
        return installed["ubuntu"]
    return next(iter(installed.values()), "Ubuntu")


def ensure_drvfs_drive_mounted(drive_letter: str) -> bool:
    """
    在当前 INSAR_WSL_DISTRO 内确保 Windows 盘符已挂载到 /mnt/<letter>。
    Ubuntu 默认可能不挂载 N:/K: 等网络盘；空目录 /mnt/k 不算已挂载。
    """
    letter = (drive_letter or "").strip().lower()
    if not letter or len(letter) != 1 or not letter.isalpha():
        return False
    mount_point = f"/mnt/{letter}"
    if _wsl_is_drvfs_mounted(mount_point):
        return True
    drive_upper = letter.upper()
    safe_mp = mount_point.replace("'", "'\"'\"'")
    bash_cmd = (
        f"mkdir -p '{safe_mp}' 2>/dev/null; "
        f"mount -t drvfs '{drive_upper}:' '{safe_mp}' 2>/dev/null || "
        f"sudo -n mount -t drvfs '{drive_upper}:' '{safe_mp}' 2>/dev/null || "
        f"sudo mount -t drvfs '{drive_upper}:' '{safe_mp}' 2>/dev/null"
    )
    argv = [_wsl_executable()]
    distro = get_wsl_distro()
    if distro:
        argv.extend(["-d", distro])
    argv.extend(["-e", "bash", "-c", bash_cmd])
    try:
        subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        logger.debug("drvfs 挂载 %s: 失败: %s", drive_upper, exc)
    ok = _wsl_is_drvfs_mounted(mount_point)
    if ok:
        logger.info("已在 WSL(%s) 挂载 %s: -> %s", distro, drive_upper, mount_point)
    return ok


def _sanitize_string(s: str) -> str:
    """移除字符串中的空字节和其他可能导致 subprocess.Popen 失败的控制字符。"""
    if not s or not isinstance(s, str):
        return s or ""
    result = s.replace("\x00", "")
    result = "".join(c for c in result if c >= " " or c in "\t\r\n")
    return result


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
    # 清理所有输入字符串中的空字节
    bash_cmd = _sanitize_string(bash_cmd)
    if wsl_distro:
        wsl_distro = _sanitize_string(wsl_distro)
    if env_script:
        env_script = _sanitize_string(env_script)

    parts = []
    # 先 export，再 source，这样 env 脚本内能读到 INSAR_PROJECT_ROOT 等并正确设置 PYTHONPATH
    if extra_env:
        for k, val in extra_env.items():
            safe = _sanitize_string(str(val)).replace("'", "'\"'\"'")
            parts.append(f"export {_sanitize_string(k)}='{safe}'")
    if env_script:
        if env_script.strip().startswith("~/"):
            suffix = env_script.strip()[2:].replace('"', '\\"')
            parts.append(f'source "$HOME/{suffix}"')
        else:
            safe = env_script.replace("'", "'\"'\"'")
            parts.append(f"source '{safe}'")
    parts.append(bash_cmd)
    inner = " && ".join(parts)
    # 若本进程本身已在 Linux/WSL 内运行，则无需再通过 wsl.exe 桥接，直接 bash 执行即可
    if os.name != "nt":
        return ["bash", "-lc", inner]

    argv = [_wsl_executable()]
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
    # 清理所有输入字符串中的空字节，防止 subprocess.Popen 失败
    bash_cmd = _sanitize_string(bash_cmd)
    if cwd:
        cwd = _sanitize_string(cwd)
    if env_script:
        env_script = _sanitize_string(env_script)

    if cwd:
        # 单引号转义：' -> '"'"'
        safe_cwd = cwd.replace("'", "'\"'\"'")
        bash_cmd = f"cd '{safe_cwd}' && {bash_cmd}"
    wsl_distro = get_wsl_distro()
    if wsl_distro:
        wsl_distro = _sanitize_string(wsl_distro)
    argv = build_wsl_argv(bash_cmd, wsl_distro=wsl_distro, env_script=env_script, extra_env=extra_env)

    # 最终清理：确保 argv 中每个元素都不包含空字节
    argv = [_sanitize_string(arg) for arg in argv]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    # 清理环境变量中的空字节（防止从 os.environ 继承的值包含空字节）
    env = {k: _sanitize_string(v) if isinstance(v, str) else v for k, v in env.items()}

    # 调试：记录 argv 中各元素的长度和是否包含空字节，便于排查 embedded null character
    for i, arg in enumerate(argv):
        if "\x00" in arg:
            logger.error("argv[%d] 包含空字节! len=%d, repr=%r", i, len(arg), arg)

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
            if hasattr(subprocess, "CREATE_NO_WINDOW") and os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            try:
                proc = subprocess.Popen(argv, **kwargs)
            except (OSError, PermissionError):
                # 部分环境（杀毒/组策略）会拦截带 CREATE_NO_WINDOW 的子进程，去掉该标志重试一次
                if "creationflags" in kwargs:
                    del kwargs["creationflags"]
                    proc = subprocess.Popen(argv, **kwargs)
                else:
                    raise
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
                        logger.warning("WSL 命令超时: argv=%s", argv)
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
            try:
                result = subprocess.run(argv, **kwargs_run)
            except (OSError, PermissionError):
                if "creationflags" in kwargs_run:
                    del kwargs_run["creationflags"]
                    result = subprocess.run(argv, **kwargs_run)
                else:
                    raise
            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "error_message": None if result.returncode == 0 else ((result.stderr or result.stdout or "").strip() or "命令返回非零"),
            }
    except FileNotFoundError as e:
        logger.error("WSL 可执行文件未找到: %s", e)
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": f"无法启动 WSL（未找到可执行文件）: {e}",
        }
    except (OSError, PermissionError) as e:
        err_msg = str(e)
        errno_val = getattr(e, "errno", None)
        winerror_val = getattr(e, "winerror", None)
        argv0 = argv[0] if argv else ""
        argv0_exists = False
        try:
            argv0_exists = bool(argv0) and os.path.isfile(argv0)
        except Exception:
            argv0_exists = False
        runtime = f"os.name={os.name}, platform={sys.platform}, exe={sys.executable}"
        # 仅当确认为权限/拒绝访问时才提示「权限不足」；其余情况直接展示原始错误，便于排查
        is_permission = (
            errno_val in (5, 13)
            or winerror_val == 5
            or "permission denied" in err_msg.lower()
            or "access is denied" in err_msg.lower()
            or "access denied" in err_msg.lower()
            or "拒绝访问" in err_msg
            or "权限不足" in err_msg
        )
        if is_permission:
            hint = "无法执行 WSL（权限不足或被拦截）。请确认已安装 WSL、尝试以管理员身份运行，或检查杀毒软件/组策略是否阻止运行 wsl。"
            detail = f"（{runtime}; wsl可执行文件: {argv0!r}, exists={argv0_exists}; 原始错误: {err_msg}）"
            logger.error("WSL 权限错误: %s", detail)
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "",
                "error_message": hint + " " + detail,
            }
        logger.error("WSL 执行错误: %s; argv0=%s, exists=%s", err_msg, argv0, argv0_exists)
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error_message": f"执行 WSL 时出错: {runtime}; {err_msg}",
        }
    except subprocess.TimeoutExpired as e:
        # 尽可能返回超时前的输出，帮助定位卡点
        out = getattr(e, "stdout", "") or ""
        err = getattr(e, "stderr", "") or ""
        argv_s = " ".join([str(x) for x in (argv or [])])
        t = "None" if timeout is None else str(timeout)
        logger.warning("WSL 命令超时 (%ss): argv=%s", t, argv_s)
        return {
            "success": False,
            "returncode": -1,
            "stdout": out,
            "stderr": err,
            "error_message": f"命令超时（{t}s）。argv={argv_s}",
        }
    except Exception as e:
        logger.exception("WSL 执行异常: %s", e)
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
        argv = [_wsl_executable()]
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
    """将 INSAR_PROJECT_ROOT（Windows 路径）转为 WSL 路径。先尝试 wslpath，失败则用本项目的 Windows→WSL 规则。"""
    win_root = (os.environ.get("INSAR_PROJECT_ROOT") or "").strip()
    if not win_root:
        return None
    win_path = win_root.replace("\\", "/").strip()
    wsl_distro = get_wsl_distro()
    argv = [_wsl_executable()]
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
    # wslpath 不可用或失败时，用与 windows_path_to_wsl 一致的规则推导（如 D:\x -> /mnt/d/x）
    return windows_path_to_wsl(win_root)


def get_wsl_project_root() -> Optional[str]:
    """
    返回 WSL 侧项目代码根路径（用于 cd 和 dem.py 等）。
    优先用 INSAR_WSL_PROJECT_ROOT；未设置时用 wslpath 将 INSAR_PROJECT_ROOT（Windows）转为 WSL 路径。
    """
    wsl_root = (os.environ.get("INSAR_WSL_PROJECT_ROOT") or "").strip()
    if wsl_root:
        return wsl_root
    return _resolve_windows_project_root_to_wsl()


def _read_isce2_main_from_libpath_doc(project_root: str) -> Optional[str]:
    """从 docs/LibPath.md 读取 isce2 源码路径（若存在且含 dem.py）。"""
    doc_path = os.path.join(project_root, "docs", "LibPath.md")
    if not os.path.isfile(doc_path):
        return None
    try:
        with open(doc_path, encoding="utf-8") as f:
            lines = [ln.strip() for ln in f.readlines()]
        for i, line in enumerate(lines):
            low = line.lower()
            if "isce2" in low and "path" in low:
                for j in range(i + 1, len(lines)):
                    cand = lines[j].strip()
                    if not cand or cand.startswith("#"):
                        continue
                    cand = os.path.abspath(cand)
                    dem_py = os.path.join(cand, "applications", "dem.py")
                    if os.path.isfile(dem_py):
                        return cand
                    break
    except OSError:
        return None
    return None


def _default_insar_project_root() -> str:
    """backend/services 上两级为 insar-system 工程根。"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def get_isce2_main_windows() -> Optional[str]:
    """
    解析本机 ISCE2 源码根目录（含 applications/dem.py）。
    顺序：INSAR_ISCE2_MAIN → 工程 lib/isce2-main → docs/LibPath.md。
    """
    explicit = (os.environ.get("INSAR_ISCE2_MAIN") or "").strip()
    if explicit:
        dem_py = os.path.join(explicit, "applications", "dem.py")
        if os.path.isfile(dem_py):
            return os.path.abspath(explicit)

    roots: List[str] = []
    env_root = (os.environ.get("INSAR_PROJECT_ROOT") or "").strip()
    if env_root:
        roots.append(env_root)
    default_root = _default_insar_project_root()
    if default_root not in roots:
        roots.append(default_root)
    for project_root in roots:
        default = os.path.join(project_root, "lib", "isce2-main")
        dem_py = os.path.join(default, "applications", "dem.py")
        if os.path.isfile(dem_py):
            return os.path.abspath(default)
        from_doc = _read_isce2_main_from_libpath_doc(project_root)
        if from_doc:
            return from_doc
    return None


def bootstrap_isce2_main_env() -> None:
    """
    非 WSL 模式：从 docs/LibPath.md 填入 INSAR_ISCE2_MAIN（Windows 源码树）。
    WSL 模式：ISCE2 由 resolve_isce2_main_wsl / resolve_tops_stack_wsl 在 Ubuntu conda 内解析，不在此写入 /mnt 路径。
    """
    if use_wsl():
        return
    if (os.environ.get("INSAR_ISCE2_MAIN") or "").strip():
        return
    path = get_isce2_main_windows()
    if path:
        os.environ["INSAR_ISCE2_MAIN"] = path
        logger.info("已自动设置 INSAR_ISCE2_MAIN=%s", path)


def _is_wsl_native_path(path: str) -> bool:
    """WSL 本机路径（非 /mnt 下 Windows 盘挂载）。"""
    p = (path or "").strip()
    return bool(p) and not p.startswith("/mnt/")


def _has_stack_sentinel(dir_path: str) -> bool:
    return os.path.isfile(os.path.join(dir_path, "stackSentinel.py"))


def get_tops_stack_pythonpath(tops_stack_dir: str) -> str:
    """
    供 `import topsStack` 使用的 PYTHONPATH 目录。
    conda 布局为 .../share/isce2/topsStack/stackSentinel.py → 应加入 .../share/isce2。
    """
    p = (tops_stack_dir or "").strip().rstrip("/\\")
    if not p:
        return ""
    if os.path.basename(p.replace("\\", "/")) == "topsStack":
        return os.path.dirname(p).replace("\\", "/")
    return p.replace("\\", "/")


def _tops_stack_from_conda_prefix() -> Optional[str]:
    prefix = (os.environ.get("CONDA_PREFIX") or "").strip().rstrip("/")
    if not prefix:
        return None
    tops = os.path.join(prefix, "share", "isce2", "topsStack")
    if _has_stack_sentinel(tops):
        return tops
    return None


def get_tops_stack_dir_for_root(project_root: str) -> Optional[str]:
    """
    解析 topsStack（stackSentinel.py）。仅 WSL conda / 显式环境变量，不用 Windows LibPath。
    """
    del project_root  # 保留参数以兼容 run_stack_wsl 调用签名
    for key in ("INSAR_ISCE2_TOPS_STACK", "INSAR_WSL_ISCE2_TOPS_STACK"):
        tops = (os.environ.get(key) or "").strip().rstrip("/\\")
        if tops and _is_wsl_native_path(tops) and _has_stack_sentinel(tops):
            return tops
    return _tops_stack_from_conda_prefix()


def _wsl_test_file_exists(wsl_path: str) -> bool:
    """在 WSL 内检查文件是否存在。"""
    safe = wsl_path.replace("'", "'\"'\"'")
    bash_cmd = f"test -f '{safe}'"
    argv = [_wsl_executable()]
    distro = get_wsl_distro()
    if distro:
        argv.extend(["-d", distro])
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
        return r.returncode == 0
    except Exception:
        return False


def _conda_activate_bash_parts(env_script: Optional[str] = None) -> List[str]:
    """WSL bash 中激活 isce2 conda 与前序 env 脚本的命令片段。"""
    parts: List[str] = []
    if env_script:
        if env_script.strip().startswith("~/"):
            suffix = env_script.strip()[2:].replace('"', '\\"')
            parts.append(f'source "$HOME/{suffix}" 2>/dev/null || true')
        else:
            safe = env_script.replace("'", "'\"'\"'")
            parts.append(f"source '{safe}' 2>/dev/null || true")
    parts.append(
        'if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then '
        'source "$HOME/miniconda3/etc/profile.d/conda.sh" && conda activate isce2 2>/dev/null; fi'
    )
    return parts


def _run_conda_python_in_wsl(py_snippet: str, env_script: Optional[str] = None) -> Optional[str]:
    parts = _conda_activate_bash_parts(env_script)
    parts.append(f'python3 -c "{py_snippet}" 2>/dev/null')
    inner = " && ".join(parts)
    argv = [_wsl_executable()]
    distro = get_wsl_distro()
    if distro:
        argv.extend(["-d", distro])
    argv.extend(["-e", "bash", "-c", inner])
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        out = (r.stdout or "").strip().splitlines()
        if out and out[-1].strip():
            return out[-1].strip().rstrip("/")
    except Exception as exc:
        logger.debug("WSL conda python 探测失败: %s", exc)
    return None


def _discover_isce2_main_from_conda_wsl(env_script: Optional[str] = None) -> Optional[str]:
    """
    在 WSL 内用 conda 环境 isce2 定位 dem.py 所在包根（site-packages/isce）。
    """
    py_snippet = (
        "import os, isce; "
        "d=os.path.join(os.path.dirname(isce.__file__), 'applications'); "
        "print(os.path.dirname(d) if os.path.isfile(os.path.join(d, 'dem.py')) else '')"
    )
    return _run_conda_python_in_wsl(py_snippet, env_script)


def _discover_tops_stack_from_conda_wsl(env_script: Optional[str] = None) -> Optional[str]:
    """在 WSL conda isce2 中定位 share/isce2/topsStack（stackSentinel.py）。"""
    py_snippet = (
        "import os; "
        "p=os.environ.get('CONDA_PREFIX',''); "
        "t=os.path.join(p,'share','isce2','topsStack') if p else ''; "
        "print(t if t and os.path.isfile(os.path.join(t,'stackSentinel.py')) else '')"
    )
    return _run_conda_python_in_wsl(py_snippet, env_script)


def resolve_tops_stack_wsl() -> tuple[Optional[str], Optional[str]]:
    """
    在 WSL Ubuntu conda isce2 内定位 topsStack（stackSentinel.py），不使用 /mnt 下 Windows 源码。
    返回 (wsl_path, error_message)。
    """
    load_wsl_config_env()
    env_script = get_wsl_env_script()

    for key in ("INSAR_WSL_ISCE2_TOPS_STACK", "INSAR_ISCE2_TOPS_STACK"):
        tops = (os.environ.get(key) or "").strip().rstrip("/")
        if not tops or not _is_wsl_native_path(tops):
            continue
        if _wsl_test_file_exists(f"{tops}/stackSentinel.py"):
            return tops, None

    conda_tops = _discover_tops_stack_from_conda_wsl(env_script)
    if conda_tops and _wsl_test_file_exists(f"{conda_tops}/stackSentinel.py"):
        os.environ.setdefault("INSAR_ISCE2_TOPS_STACK", conda_tops)
        return conda_tops, None

    distro = get_wsl_distro() or "Ubuntu"
    return None, (
        "未在 WSL 内找到 stackSentinel.py（topsStack）。\n"
        f"请确认 {distro} 中已安装 conda 环境 isce2（scripts/wsl/setup_isce2_ubuntu24.sh），\n"
        "且存在 $CONDA_PREFIX/share/isce2/topsStack/stackSentinel.py。\n"
        "可设置 INSAR_WSL_ISCE2_TOPS_STACK 为 WSL 本机路径（勿用 /mnt/... 下 Windows 源码树）。"
    )


def build_wsl_isce2_extra_env() -> tuple[Dict[str, str], Optional[str]]:
    """为 run_wsl 构造 WSL 本机 ISCE2 环境变量（不含 /mnt 下 INSAR_ISCE2_MAIN）。"""
    main, main_err = resolve_isce2_main_wsl()
    if main_err or not main:
        return {}, main_err or "未找到 WSL ISCE2 环境。"
    tops, tops_err = resolve_tops_stack_wsl()
    if tops_err or not tops:
        return {}, tops_err or "未找到 WSL topsStack。"
    stack_pp = get_tops_stack_pythonpath(tops)
    return {
        "INSAR_WSL_ISCE2_MAIN": main,
        "INSAR_ISCE2_TOPS_STACK": tops,
        "INSAR_ISCE2_STACK_PYTHONPATH": stack_pp,
    }, None


def resolve_isce2_main_wsl() -> tuple[Optional[str], Optional[str]]:
    """
    返回 WSL Ubuntu conda isce2 内 ISCE 包根（site-packages/isce，含 applications/dem.py）。
    不使用 /mnt 下 Windows 源码或 docs/LibPath.md。
    """
    load_wsl_config_env()
    env_script = get_wsl_env_script()
    candidates: list[str] = []

    conda_root = _discover_isce2_main_from_conda_wsl(env_script)
    if conda_root and _is_wsl_native_path(conda_root):
        candidates.append(conda_root.rstrip("/"))

    wsl_explicit = (os.environ.get("INSAR_WSL_ISCE2_MAIN") or "").strip().rstrip("/")
    if wsl_explicit and _is_wsl_native_path(wsl_explicit):
        candidates.append(wsl_explicit)

    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        dem_wsl = f"{cand}/applications/dem.py"
        if _wsl_test_file_exists(dem_wsl):
            os.environ.setdefault("INSAR_WSL_ISCE2_MAIN", cand)
            return cand, None

    distro = get_wsl_distro() or "Ubuntu"
    return None, (
        "未在 WSL 内找到 ISCE2 dem.py。\n"
        f"请确认 {distro} 中 conda 环境 isce2 已安装（scripts/wsl/setup_isce2_ubuntu24.sh），\n"
        "或设置 INSAR_WSL_ISCE2_MAIN 为 WSL 本机 site-packages/isce 路径（勿用 /mnt/...）。"
    )


def check_wsl_project_root() -> Dict[str, object]:
    """
    检查 WSL 项目根是否正确：是否已设置、在 WSL 内是否存在、是否包含 MintPy 源码（或已安装 mintpy）。
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
    argv = [_wsl_executable()]
    if wsl_distro:
        argv.extend(["-d", wsl_distro])
    # 在 WSL 内检查目录存在且包含 MintPy 源码（优先 INSAR_WSL_MINTPY_SRC），或可 import mintpy
    safe_root = root.replace("'", "'\"'\"'")
    bash_cmd = (
        f"ROOT=\"$(eval echo {safe_root})\"; "
        f"MINTPY_SRC=\"${{INSAR_WSL_MINTPY_SRC:-$ROOT/lib/MintPy-main/src}}\"; "
        f"[ -d \"$ROOT\" ] && ( [ -d \"$MINTPY_SRC/mintpy\" ] || python3 -c \"import mintpy\" >/dev/null 2>&1 ) && echo OK || echo FAIL"
    )
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
    except (OSError, PermissionError) as e:
        if "13" in str(e) or "Permission denied" in str(e):
            return {
                "ok": False,
                "message": "无法执行 WSL（权限不足或被拦截）。请尝试以管理员身份运行或检查杀毒软件/组策略。",
                "path": root,
                "mintpy_src_exists": None,
            }
        return {
            "ok": False,
            "message": str(e),
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
