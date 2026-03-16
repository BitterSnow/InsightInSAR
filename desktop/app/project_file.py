"""
解析与校验项目文件：优先 YAML（.yaml），兼容 .md。
支持可选「工作区」：一行 N,S,W,E（北纬、南纬、西经、东经）。
打开旧工程时若仅有 .md，会自动迁移为 .yaml 后返回 .yaml 路径。
"""
from __future__ import annotations

import re
from pathlib import Path

from . import project_yaml

REQUIRED_SECTIONS = ["项目名称", "项目id", "雷达数据类型", "建立时间", "项目完整路径"]
WORKSPACE_SECTION = "工作区"  # 可选，值为一行 "N,S,W,E"
# 数据导入面板可选预填路径与参数（工程 .md 中若有对应 # 标题 则解析并预填）
DATA_IMPORT_PATH_KEYS = ("SAFE ZIP 路径", "轨道目录", "DEM 路径", "Aux 目录")
DATA_IMPORT_PARAM_KEYS = ("Swaths", "极化")
# 处理步骤字段
PROCESSING_STEPS_SECTION = "处理步骤"
ALLOWED_RADAR_TYPES = ("Sentinel-1",)


def _is_windows_absolute_path(path: str) -> bool:
    s = path.strip().replace("\\", "/")
    return bool(re.match(r"^[a-zA-Z]:/", s))


def _parse_all_sections(content: str) -> dict[str, str]:
    """解析 .md 中所有 # 标题段落，返回 { 标题: 内容 }。"""
    result: dict[str, str] = {}
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("# "):
            header = line.strip()[2:].strip()
            value_parts = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("#"):
                value_parts.append(lines[i])
                i += 1
            result[header] = "\n".join(value_parts).strip()
            continue
        i += 1
    return result


def parse_project_md(content: str) -> dict[str, str] | None:
    """
    解析 .md 内容，返回 { 项目名称, 项目id, ... }（含可选 工作区）。
    缺少任一必需段时返回 None。
    """
    result = _parse_all_sections(content)
    if set(REQUIRED_SECTIONS) - set(result.keys()):
        return None
    return result


def validate_project_data(data: dict[str, str]) -> tuple[bool, str]:
    """
    校验解析结果。返回 (是否通过, 错误信息)。
    """
    for key in REQUIRED_SECTIONS:
        val = data.get(key, "").strip()
        if not val:
            return False, f"缺少或为空：{key}"

    path_val = data["项目完整路径"].strip()
    if not _is_windows_absolute_path(path_val):
        return False, "项目完整路径须为 Windows 绝对路径（如 D:\\文件夹\\项目名）"

    radar = data["雷达数据类型"].strip()
    if radar not in ALLOWED_RADAR_TYPES:
        return False, f"不支持的雷达数据类型：{radar}，当前支持：{', '.join(ALLOWED_RADAR_TYPES)}"

    return True, ""


def load_and_validate(file_path: str | Path) -> tuple[dict | None, str]:
    """
    读取工程文件（.yaml 或 .md）并校验。返回 (解析后的数据, 错误信息)。
    成功时错误信息为空；失败时数据为 None。
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None, "文件不存在"
    if path.suffix.lower() == ".yaml":
        data = project_yaml.load_project(path)
        if data is None:
            return None, "项目 YAML 格式不符或缺少必要字段"
        ok, err = project_yaml.validate_project_data(data)
        if not ok:
            return None, err
        return data, ""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return None, f"读取文件失败：{e}"
    data = parse_project_md(content)
    if data is None:
        return None, "项目文件格式不符，缺少必要字段（项目名称、项目id、雷达数据类型、建立时间、项目完整路径）"
    ok, err = validate_project_data(data)
    if not ok:
        return None, err
    return data, ""


def safe_md_filename(name: str) -> str:
    """与后端一致：生成可用于 .md 文件名的安全字符串。"""
    s = re.sub(r'[<>:"/\\|?*]', "_", name.strip())
    return s[:200] if s else "project"


def find_md_path(project_dir: str | Path, project_id: str) -> Path | None:
    """
    在项目目录下查找包含指定 项目id 的 .md 文件。
    返回该文件路径，未找到返回 None。
    """
    dir_path = Path(project_dir)
    if not dir_path.is_dir():
        return None
    for f in dir_path.glob("*.md"):
        try:
            data = parse_project_md(f.read_text(encoding="utf-8"))
            if data and data.get("项目id", "").strip() == project_id.strip():
                return f
        except Exception:
            continue
    return None


def find_project_path(project_dir: str | Path, project_id: str) -> Path | None:
    """
    统一查找工程文件：优先 .yaml，若无则查找 .md 并自动迁移为 .yaml 后返回 .yaml 路径。
    返回工程文件路径（.yaml 或 .md），未找到返回 None。
    """
    dir_path = Path(project_dir)
    if not dir_path.is_dir():
        return None
    pid = (project_id or "").strip()
    # 1) 先找 .yaml
    yaml_path = project_yaml.find_project_path(dir_path, pid)
    if yaml_path is not None:
        return yaml_path
    # 2) 再找 .md，找到则迁移为 .yaml
    md_path = find_md_path(dir_path, pid)
    if md_path is None:
        return None
    try:
        data = load_project_md_full(md_path)
        if not data:
            return md_path
        name = (data.get("项目名称") or data.get("name") or "").strip()
        safe_name = project_yaml.safe_yaml_filename(name) or "project"
        yaml_path = dir_path / f"{safe_name}.yaml"
        project_yaml.write_project(yaml_path, data)
        return yaml_path
    except Exception:
        return md_path


def write_project_md(file_path: str | Path, data: dict[str, str]) -> None:
    """
    将项目数据写入 .md 文件。data 需包含 REQUIRED_SECTIONS 全部键；
    可选键 工作区（一行 N,S,W,E）会一并写入。
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# 项目名称
{data["项目名称"]}

# 项目id
{data["项目id"]}

# 雷达数据类型
{data["雷达数据类型"]}

# 建立时间
{data["建立时间"]}

# 项目完整路径
{data["项目完整路径"]}
"""
    if data.get(WORKSPACE_SECTION):
        content += f"""
# {WORKSPACE_SECTION}
{data[WORKSPACE_SECTION]}
"""
    for key in DATA_IMPORT_PATH_KEYS + DATA_IMPORT_PARAM_KEYS:
        if data.get(key, "").strip():
            content += f"""
# {key}
{data[key].strip()}
"""
    # 写入处理步骤
    if data.get(PROCESSING_STEPS_SECTION, "").strip():
        content += f"""
# {PROCESSING_STEPS_SECTION}
{data[PROCESSING_STEPS_SECTION].strip()}
"""
    path.write_text(content, encoding="utf-8")


def validate_workspace_coords(n: float, s: float, w: float, e: float) -> tuple[bool, str]:
    """
    校验工作区四至：N/S 纬度，W/E 经度。返回 (是否合法, 错误信息)。
    """
    if s > n:
        return False, "南纬(S) 不能大于北纬(N)"
    if w > e:
        return False, "西经(W) 不能大于东经(E)"
    if not (-90 <= s <= 90 and -90 <= n <= 90):
        return False, "纬度 N、S 应在 -90 ～ 90 之间"
    if not (-180 <= w <= 180 and -180 <= e <= 180):
        return False, "经度 W、E 应在 -180 ～ 180 之间"
    return True, ""


def load_project_md_full(file_path: str | Path) -> dict[str, str] | None:
    """
    读取工程文件全部内容（.yaml 或 .md），返回兼容层 dict（含 项目名称、项目id 等）。
    缺少必需段时返回 None。
    """
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None
    if path.suffix.lower() == ".yaml":
        data = project_yaml.load_project(path)
        if data is None:
            return None
        if set(REQUIRED_SECTIONS) - set(data.keys()):
            return None
        return data
    try:
        raw = _parse_all_sections(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if set(REQUIRED_SECTIONS) - set(raw.keys()):
        return None
    return raw


def write_project(file_path: str | Path, data: dict) -> None:
    """
    将工程数据写入文件。根据扩展名写入 .yaml 或 .md。
    data 需包含 REQUIRED_SECTIONS 全部键（或 YAML 对应键）。
    """
    path = Path(file_path)
    if path.suffix.lower() == ".yaml":
        project_yaml.write_project(path, data)
    else:
        write_project_md(path, data)

