"""
将 Windows 侧 CDS 配置同步到 WSL ~/.cdsapirc（供 Desktop / 部署向导 / MintPy 使用）。
"""
from __future__ import annotations

import base64
import os
import subprocess
from typing import Callable, Optional

from wsl_config_path import DEFAULT_CDS_URL, cdsapirc_content, read_cdsapirc_windows

DecodeFn = Callable[[bytes | None], str]


def _wsl_exe() -> str:
    if os.name != "nt":
        return "wsl"
    sysroot = os.environ.get("SystemRoot", "C:\\Windows")
    full = os.path.join(sysroot, "System32", "wsl.exe")
    return full if os.path.isfile(full) else "wsl.exe"


def _default_decode(data: bytes | None) -> str:
    if not data:
        return ""
    for enc in ("utf-8-sig", "utf-8", "gbk", "cp936", "latin-1"):
        try:
            return data.decode(enc, errors="strict").strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace").strip()


def push_cdsapirc_to_wsl(
    distro: str,
    api_key: str,
    url: str = DEFAULT_CDS_URL,
    *,
    decode: Optional[DecodeFn] = None,
    creationflags: int = 0,
    timeout: int = 60,
) -> tuple[bool, str]:
    if os.name != "nt":
        return True, "非 Windows，跳过 WSL CDS 同步"
    decode = decode or _default_decode
    content = cdsapirc_content(api_key, url)
    b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
    inner = (
        "mkdir -p \"$HOME\" && "
        f"echo '{b64}' | base64 -d > \"$HOME/.cdsapirc\" && "
        "chmod 600 \"$HOME/.cdsapirc\" && "
        "test -f \"$HOME/.cdsapirc\" && echo CDS_WSL_OK"
    )
    argv = [_wsl_exe(), "-d", distro, "-e", "bash", "-c", inner]
    try:
        r = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout,
            creationflags=creationflags,
        )
        out = decode(r.stdout) or decode(r.stderr)
        if r.returncode != 0 or "CDS_WSL_OK" not in (out or ""):
            return False, (out or "写入 WSL ~/.cdsapirc 失败").strip()
        return True, "已同步 CDS 配置到 WSL"
    except Exception as e:
        return False, str(e)


def sync_cdsapirc_from_windows_to_wsl(
    distro: str,
    *,
    decode: Optional[DecodeFn] = None,
    creationflags: int = 0,
) -> tuple[bool, str]:
    parsed = read_cdsapirc_windows()
    if not parsed:
        return True, "未配置 CDS"
    url, key = parsed
    return push_cdsapirc_to_wsl(distro, key, url, decode=decode, creationflags=creationflags)
