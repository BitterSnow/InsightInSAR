"""
InSAR 本机用户配置路径（%LOCALAPPDATA%\\InSAR）。
供部署向导、Desktop 与 WSL 桥接共用；勿将 CDS 凭据写入 WSL 镜像。
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional, Tuple

DEFAULT_CDS_URL = "https://cds.climate.copernicus.eu/api"
CDS_REGISTER_URL = "https://cds.climate.copernicus.eu/"


def get_insar_app_data_dir() -> Path:
    local = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or "").strip()
    if local:
        return Path(local) / "InSAR"
    return Path.home() / "InSAR"


def ensure_config_dir() -> bool:
    try:
        get_insar_app_data_dir().mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def get_wsl_config_path() -> Optional[Path]:
    return get_insar_app_data_dir() / "wsl_config.env"


def get_cdsapirc_path() -> Path:
    return get_insar_app_data_dir() / "cdsapirc"


def get_weather_dir_path() -> Path:
    return get_insar_app_data_dir() / "weather"


def cdsapirc_content(api_key: str, url: str = DEFAULT_CDS_URL) -> str:
    key = (api_key or "").strip()
    if not key:
        raise ValueError("CDS API key 不能为空")
    u = (url or DEFAULT_CDS_URL).strip() or DEFAULT_CDS_URL
    return f"url: {u}\nkey: {key}\n"


def write_cdsapirc_windows(api_key: str, url: str = DEFAULT_CDS_URL) -> Path:
    """写入 Windows 侧 cdsapirc（不含换行泄露到日志）。"""
    if not ensure_config_dir():
        raise OSError("无法创建 InSAR 配置目录")
    path = get_cdsapirc_path()
    content = cdsapirc_content(api_key, url)
    path.write_text(content, encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def read_cdsapirc_windows() -> Optional[Tuple[str, str]]:
    """读取 (url, key)；文件不存在或无效时返回 None。"""
    path = get_cdsapirc_path()
    if not path.is_file():
        return None
    url, key = DEFAULT_CDS_URL, ""
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("url:"):
                url = line.split(":", 1)[1].strip() or DEFAULT_CDS_URL
            elif line.startswith("key:"):
                key = line.split(":", 1)[1].strip()
    except OSError:
        return None
    if not key or key.upper().startswith("YOUR_"):
        return None
    return url, key


def cdsapirc_is_configured() -> bool:
    return read_cdsapirc_windows() is not None
