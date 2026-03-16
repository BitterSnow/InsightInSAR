"""
工程列表与当前项目的本地持久化。不依赖 FastAPI。
存储位置：项目根目录下 desktop_projects.json、desktop_current_project.txt。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .project_file import safe_md_filename, write_project

REQUIRED_SECTIONS = ["项目名称", "项目id", "雷达数据类型", "建立时间", "项目完整路径"]


def _project_root() -> Path:
    root = os.environ.get("INSAR_PROJECT_ROOT")
    if root and Path(root).is_dir():
        return Path(root)
    # desktop/app/project_store.py -> desktop -> project root
    return Path(__file__).resolve().parent.parent.parent


def _projects_file() -> Path:
    return _project_root() / "desktop_projects.json"


def _current_file() -> Path:
    return _project_root() / "desktop_current_project.txt"


def load_projects() -> list[dict]:
    """加载工程列表。每项 { id, name, radarType, projectPath }。"""
    path = _projects_file()
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def save_projects(projects: list[dict]) -> None:
    """保存工程列表。"""
    _projects_file().write_text(
        json.dumps(projects, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_current_project_path() -> str | None:
    """当前选中的项目路径；无则返回 None。"""
    path = _current_file()
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except Exception:
        return None


def set_current_project_path(project_path: str) -> None:
    """设置当前项目路径。"""
    _current_file().write_text(project_path.strip(), encoding="utf-8")


def create_project_local(name: str, radar_type: str, project_path: str) -> dict:
    """
    在本地创建工程：创建目录、写入 .md、加入列表并保存，并设为当前项目。
    返回节点 dict：{ id, name, radarType, projectPath }（与主窗口 _projects 项一致）。
    """
    project_path = project_path.strip().replace("/", os.sep).rstrip(os.sep)
    project_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_name = safe_md_filename(name)
    file_name = f"{safe_name}.yaml"
    base_dir = Path(project_path)
    base_dir.mkdir(parents=True, exist_ok=True)
    project_file_path = base_dir / file_name
    data = {
        "项目名称": name,
        "项目id": project_id,
        "雷达数据类型": radar_type,
        "建立时间": created_at,
        "项目完整路径": project_path,
    }
    write_project(project_file_path, data)
    node = {
        "id": project_id,
        "name": name,
        "radarType": radar_type,
        "projectPath": project_path,
    }
    projects = load_projects()
    projects.append(node)
    save_projects(projects)
    set_current_project_path(project_path)
    return node


def add_project_node(node: dict) -> None:
    """将已有工程节点加入列表并保存（如从「打开工程」加载的 .md）。"""
    projects = load_projects()
    if any(p.get("id") == node.get("id") for p in projects):
        return
    projects.append(node)
    save_projects(projects)


def update_project_node(node: dict) -> None:
    """按 id 更新列表中对应节点并保存。"""
    projects = load_projects()
    for i, p in enumerate(projects):
        if p.get("id") == node.get("id"):
            projects[i] = node
            save_projects(projects)
            return
