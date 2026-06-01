"""
MintPy velocity / timeseries → 矢量导出（GeoPackage / Shapefile）。
Windows 桌面通过 WSL 执行（conda GDAL）；非 WSL 模式尝试本机 osgeo。
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

from backend.services import wsl_runner

logger = logging.getLogger(__name__)


def _parse_json_stdout(stdout: str) -> Dict[str, Any]:
    text = (stdout or "").strip()
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            return json.loads(line)
    raise ValueError("WSL 未返回有效 JSON 结果")


def _resolve_windows_file_to_wsl(windows_path: str) -> tuple[Optional[str], Optional[str]]:
    raw = (windows_path or "").strip()
    if not raw:
        return None, "路径为空。"
    if not os.path.isfile(raw):
        return None, f"文件不存在: {raw}"
    wsl_runner.load_wsl_config_env()
    m_drive = re.match(r"^([a-zA-Z])\s*:", raw.replace("/", "\\"))
    if m_drive:
        wsl_runner.ensure_drvfs_drive_mounted(m_drive.group(1))
    wsl_path = wsl_runner.windows_path_to_wsl(os.path.abspath(raw))
    if wsl_runner._wsl_test_file_exists(wsl_path):
        return wsl_path, None
    distro = wsl_runner.get_wsl_distro() or "Ubuntu"
    return None, f"WSL（{distro}）无法访问文件: {raw}"


def _resolve_windows_dir_to_wsl(windows_path: str) -> tuple[Optional[str], Optional[str]]:
    raw = (windows_path or "").strip()
    if not raw:
        return None, "路径为空。"
    os.makedirs(raw, exist_ok=True)
    wsl_path, err = wsl_runner.resolve_windows_path_to_wsl(raw)
    if wsl_path:
        return wsl_path, None
    wsl_runner.load_wsl_config_env()
    m_drive = re.match(r"^([a-zA-Z])\s*:", raw.replace("/", "\\"))
    if m_drive:
        wsl_runner.ensure_drvfs_drive_mounted(m_drive.group(1))
    wsl_path = wsl_runner.windows_path_to_wsl(os.path.abspath(raw))
    if wsl_runner._wsl_test_dir_exists(wsl_path):
        return wsl_path, None
    return None, err or f"WSL 无法访问目录: {raw}"


def run_mintpy_vector_export(
    vel_path: str,
    h5_path: str,
    out_dir: str,
    pixel_span: int = 1,
    output_format: str = "gpkg",
    max_points: int = 0,
    timeout: int = 7200,
) -> Dict[str, Any]:
    """
    导出 MintPy 点矢量。WSL 模式下在 Ubuntu conda 内运行（需 GDAL/GPKG）。

    Returns:
        {"success", "count", "output_path", "error_message", ...}
    """
    if not wsl_runner.use_wsl():
        try:
            from backend.tools.mintpy_to_shapefile import run_mintpy_to_shapefile

            count, out_file = run_mintpy_to_shapefile(
                vel_path, h5_path, out_dir, pixel_span=pixel_span, output_format=output_format,
                max_points=max_points,
            )
            return {"success": True, "count": count, "output_path": out_file}
        except ImportError as e:
            return {
                "success": False,
                "error_message": (
                    "本机未安装 GDAL (osgeo)。请使用 WSL 模式启动桌面（scripts/start_desktop_wsl.bat），"
                    "或在当前 Python 环境安装：conda install gdal"
                ),
            }
        except Exception as e:
            logger.exception("MintPy 转矢量失败（本机）")
            return {"success": False, "error_message": str(e)}

    vel_wsl, err = _resolve_windows_file_to_wsl(vel_path)
    if err:
        return {"success": False, "error_message": err}
    h5_wsl, err = _resolve_windows_file_to_wsl(h5_path)
    if err:
        return {"success": False, "error_message": err}
    out_wsl, err = _resolve_windows_dir_to_wsl(out_dir)
    if err:
        return {"success": False, "error_message": err}

    project_root = wsl_runner.get_wsl_project_root()
    if not project_root:
        return {"success": False, "error_message": "未配置 INSAR_WSL_PROJECT_ROOT，无法定位工程根目录。"}

    payload = {
        "vel_path": vel_wsl,
        "h5_file_path": h5_wsl,
        "out_dir": out_wsl,
        "pixel_span": pixel_span,
        "output_format": output_format,
        "max_points": max_points,
    }
    env_script = wsl_runner.get_wsl_env_script()
    cmd = (
        f"cd '{project_root}' && PYTHONPATH='.' INSAR_PROJECT_ROOT='{project_root}' "
        f"python3 -m backend.scripts.run_mintpy_to_shapefile_wsl"
    )
    logger.info(
        "MintPy 转矢量 WSL: vel=%s ts=%s out=%s format=%s span=%s max_pts=%s",
        vel_wsl,
        h5_wsl,
        out_wsl,
        output_format,
        pixel_span,
        max_points,
    )
    result = wsl_runner.run_wsl(
        cmd,
        env_script=env_script,
        extra_env={"INSAR_MINTPY_VECTOR_JSON": json.dumps(payload)},
        timeout=timeout,
    )
    if not result.get("success"):
        return {
            "success": False,
            "error_message": (result.get("error_message") or result.get("stderr") or "WSL 执行失败").strip(),
            "stdout": result.get("stdout"),
            "stderr": result.get("stderr"),
        }
    try:
        data = _parse_json_stdout(str(result.get("stdout") or ""))
    except (json.JSONDecodeError, ValueError) as e:
        stderr = (result.get("stderr") or "").strip()
        return {
            "success": False,
            "error_message": f"解析 WSL 输出失败: {e}" + (f"\n{stderr}" if stderr else ""),
            "stdout": result.get("stdout"),
            "stderr": result.get("stderr"),
        }
    if not data.get("success"):
        return {
            "success": False,
            "error_message": data.get("error_message") or "转换失败",
        }
    out_file = data.get("output_path")
    if isinstance(out_file, str) and out_file.startswith("/mnt/"):
        out_file = wsl_runner.wsl_path_to_windows(out_file)
    return {
        "success": True,
        "count": data.get("count", 0),
        "output_path": out_file,
    }
