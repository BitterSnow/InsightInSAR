"""
工程 YAML 文件读写。与 project_file.py 的 .md 并存，优先使用 YAML。
返回的 dict 同时包含兼容旧代码的键（项目名称、项目id 等）与 YAML 原生键（name、id、steps_done 等）。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

# 必需字段（YAML 键名）
REQUIRED_KEYS = ("name", "id", "radar_type", "created_at", "project_path")
ALLOWED_RADAR_TYPES = ("Sentinel-1",)

# 旧接口兼容：.md 段名 -> YAML 或 data 键
LEGACY_TO_YAML = {
    "项目名称": "name",
    "项目id": "id",
    "雷达数据类型": "radar_type",
    "建立时间": "created_at",
    "项目完整路径": "project_path",
}
YAML_TO_LEGACY = {v: k for k, v in LEGACY_TO_YAML.items()}


def _is_windows_absolute_path(path: str) -> bool:
    s = (path or "").strip().replace("\\", "/")
    return bool(re.match(r"^[a-zA-Z]:/", s))


def safe_yaml_filename(name: str) -> str:
    """与 safe_md_filename 一致：生成可用于文件名的安全字符串。"""
    s = re.sub(r'[<>:"/\\|?*]', "_", (name or "").strip())
    return s[:200] if s else "project"


def _data_to_yaml_dict(data: dict[str, Any]) -> dict[str, Any]:
    """将兼容层 dict（含 项目名称 / name 等）转为 YAML 可写结构。"""
    out: dict[str, Any] = {}
    # 必需
    for leg, yk in LEGACY_TO_YAML.items():
        val = data.get(yk) or data.get(leg)
        if isinstance(val, str):
            val = val.strip()
        if val is not None and val != "":
            out[yk] = val
    for k in REQUIRED_KEYS:
        if k not in out:
            out[k] = data.get(k, "")
    # 工作区
    ws = data.get("workspace")
    if isinstance(ws, dict) and all(k in ws for k in ("n", "s", "w", "e")):
        out["workspace"] = {k: float(ws[k]) for k in ("n", "s", "w", "e")}
    elif data.get("工作区"):
        raw = (data.get("工作区") or "").strip()
        parts = [p.strip() for p in raw.replace("，", ",").split(",")]
        if len(parts) >= 4:
            try:
                out["workspace"] = {
                    "n": float(parts[0]),
                    "s": float(parts[1]),
                    "w": float(parts[2]),
                    "e": float(parts[3]),
                }
            except ValueError:
                pass
    # 数据目录：优先用表单/兼容键（保存到工程时由 s1_import_dialog 写入），否则用已有 data_dirs
    dd = {}
    for leg, yk in [("SAFE ZIP 路径", "safe_zip"), ("SAFE ZIP路径", "safe_zip"), ("轨道目录", "orbit"), ("DEM 路径", "dem"), ("DEM路径", "dem"), ("Aux 目录", "aux"), ("Aux目录", "aux")]:
        v = (data.get(leg) or data.get(yk) or "").strip()
        if v and yk not in dd:
            dd[yk] = v
    if not dd:
        data_dirs = data.get("data_dirs")
        if isinstance(data_dirs, dict):
            dd = {k: str(v).strip() for k, v in data_dirs.items() if v}
    if dd:
        out["data_dirs"] = dd
    # 导入参数：优先用表单/兼容键，否则用已有 import_params
    ip = {}
    for leg, yk in [("Swaths", "swaths"), ("极化", "polarization")]:
        v = (data.get(leg) or data.get(yk) or "").strip()
        if v:
            ip[yk] = v
    if not ip:
        import_params = data.get("import_params")
        if isinstance(import_params, dict):
            ip = {k: str(v).strip() for k, v in import_params.items() if v}
    if ip:
        out["import_params"] = ip
    # 流程工作目录
    for key in ("stack_work_dir", "mintpy_work_dir"):
        v = (data.get(key) or "").strip()
        if v:
            out[key] = v
    # Stack 初始化参数（初始化流程后写回，下次预填）
    if data.get("stack_init") and isinstance(data["stack_init"], dict):
        out["stack_init"] = data["stack_init"]
    # 处理步骤 / steps_done
    steps_done = data.get("steps_done")
    if isinstance(steps_done, dict):
        out["steps_done"] = steps_done
    elif data.get("处理步骤"):
        raw = (data.get("处理步骤") or "").strip()
        steps = [s.strip() for s in raw.replace(",", " ").split() if s.strip()]
        if steps:
            out["steps_done"] = {"s1_import": True, "steps_list": steps}
    return out


def _yaml_dict_to_data(raw: dict[str, Any]) -> dict[str, Any]:
    """将 YAML 解析结果转为兼容层 dict（含 项目名称、项目id、工作区 等）。"""
    data: dict[str, Any] = {}
    for yk, leg in YAML_TO_LEGACY.items():
        v = raw.get(yk)
        if v is not None:
            data[yk] = str(v).strip() if isinstance(v, str) else v
            data[leg] = data[yk]
    for k in ("name", "id", "radar_type", "created_at", "project_path"):
        if k not in data and raw.get(k) is not None:
            data[k] = str(raw[k]).strip() if isinstance(raw[k], str) else raw[k]
    # 工作区
    ws = raw.get("workspace")
    if isinstance(ws, dict):
        n, s, w, e = ws.get("n"), ws.get("s"), ws.get("w"), ws.get("e")
        if all(x is not None for x in (n, s, w, e)):
            data["workspace"] = ws
            data["工作区"] = f"{n},{s},{w},{e}"
    # 数据目录 -> 兼容键（含无空格变体供 s1_import_dialog 等使用）
    data_dirs_raw = raw.get("data_dirs") or {}
    if isinstance(data_dirs_raw, dict):
        data["data_dirs"] = {k: str(v).strip() for k, v in data_dirs_raw.items() if v}
    _dd_map = [("safe_zip", "SAFE ZIP 路径", "SAFE ZIP路径"), ("orbit", "轨道目录", None), ("dem", "DEM 路径", "DEM路径"), ("aux", "Aux 目录", "Aux目录")]
    for dd_key, leg, leg_alt in _dd_map:
        val = data_dirs_raw.get(dd_key)
        if val:
            v = str(val).strip()
            data[leg] = v
            if leg_alt:
                data[leg_alt] = v
    # 导入参数
    for ip_key, leg in [("swaths", "Swaths"), ("polarization", "极化")]:
        val = (raw.get("import_params") or {}).get(ip_key)
        if val:
            data[leg] = str(val).strip()
    # 流程工作目录
    for key in ("stack_work_dir", "mintpy_work_dir"):
        v = raw.get(key)
        if v:
            data[key] = str(v).strip()
    # Stack 初始化参数
    if raw.get("stack_init") and isinstance(raw["stack_init"], dict):
        data["stack_init"] = raw["stack_init"]
    # steps_done
    sd = raw.get("steps_done")
    if isinstance(sd, dict):
        data["steps_done"] = sd
        if sd.get("steps_list"):
            data["处理步骤"] = " ".join(sd["steps_list"])
        elif sd.get("s1_import") and not data.get("处理步骤"):
            data["处理步骤"] = "S1导入"
    return data


def validate_project_data(data: dict[str, Any]) -> tuple[bool, str]:
    """校验工程数据。返回 (是否通过, 错误信息)。"""
    path_val = (data.get("project_path") or data.get("项目完整路径") or "").strip()
    if not path_val:
        return False, "缺少项目完整路径"
    if not _is_windows_absolute_path(path_val):
        return False, "项目完整路径须为 Windows 绝对路径（如 D:\\文件夹\\项目名）"
    radar = (data.get("radar_type") or data.get("雷达数据类型") or "").strip()
    if radar and radar not in ALLOWED_RADAR_TYPES:
        return False, f"不支持的雷达数据类型：{radar}，当前支持：{', '.join(ALLOWED_RADAR_TYPES)}"
    return True, ""


def load_project(file_path: str | Path) -> dict[str, Any] | None:
    """
    从 YAML 文件加载工程，返回兼容层 dict（含 项目名称、项目id、工作区、steps_done 等）。
    文件不存在或格式错误返回 None。
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(content)
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    for k in REQUIRED_KEYS:
        if not raw.get(k):
            return None
    return _yaml_dict_to_data(raw)


def write_project(file_path: str | Path, data: dict[str, Any]) -> None:
    """将工程数据写入 YAML 文件。data 可含兼容键或 YAML 键。"""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = _data_to_yaml_dict(data)
    for k in REQUIRED_KEYS:
        if k not in out or out[k] in (None, ""):
            out[k] = data.get(YAML_TO_LEGACY.get(k, k), "")
    text = yaml.dump(
        out,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    path.write_text(text, encoding="utf-8")


def find_project_path(project_dir: str | Path, project_id: str) -> Path | None:
    """在项目目录下查找 project_id 对应的 .yaml 文件，未找到返回 None。"""
    dir_path = Path(project_dir)
    if not dir_path.is_dir():
        return None
    project_id = (project_id or "").strip()
    for f in dir_path.glob("*.yaml"):
        try:
            data = load_project(f)
            if data and (data.get("id") or data.get("项目id") or "").strip() == project_id:
                return f
        except Exception:
            continue
    return None
