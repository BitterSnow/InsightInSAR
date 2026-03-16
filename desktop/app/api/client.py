"""
与 FastAPI 后端通信的 HTTP 客户端。与 Web 端 api.ts 行为一致。
"""
from __future__ import annotations

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
NETWORK_ERROR_MSG = "无法连接后端服务，请确认 API 已启动（默认 http://localhost:8000）"


def get_client(base_url: str = DEFAULT_BASE_URL) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=30.0)


# --- 新建工程（与 POST /api/projects 一致） ---


def create_project(
    client: httpx.Client,
    *,
    name: str,
    radar_type: str,
    project_path: str,
) -> dict:
    """新建工程。project_path 须为 Windows 绝对路径。"""
    payload = {"name": name, "radar_type": radar_type, "project_path": project_path.strip()}
    try:
        r = client.post("/api/projects", json=payload)
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise RuntimeError(NETWORK_ERROR_MSG) from e
    if r.status_code != 200:
        msg = r.text
        try:
            j = r.json()
            if "detail" in j:
                msg = j["detail"] if isinstance(j["detail"], str) else str(j["detail"])
        except Exception:
            pass
        raise RuntimeError(msg or f"HTTP {r.status_code}")
    return r.json()


# --- 当前项目（GET/PUT /api/config/current-project） ---


def get_current_project(client: httpx.Client) -> str | None:
    """获取当前项目路径；无配置时返回 None。"""
    try:
        r = client.get("/api/config/current-project")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("project_path")
    except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException):
        return None


def set_current_project(client: httpx.Client, project_path: str) -> dict:
    """设置当前项目路径。"""
    r = client.put("/api/config/current-project", json={"project_path": project_path.strip()})
    r.raise_for_status()
    return r.json()


# --- Stack 流程（POST /api/stack/init, GET /api/stack/pipeline, POST run-step/run-steps） ---


def stack_init(client: httpx.Client, payload: dict) -> dict:
    """初始化 Stack：生成 configs + run_files + pipeline.json。payload = StackConfigRequest.model_dump()."""
    r = client.post("/api/stack/init", json=payload, timeout=600.0)
    if r.status_code != 200:
        try:
            j = r.json()
            detail = j.get("detail") or j.get("error_message", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(detail if isinstance(detail, str) else str(detail))
    return r.json()


def stack_load_pipeline(client: httpx.Client, work_dir: str) -> dict:
    """读取 work_dir 下的 pipeline.json。"""
    r = client.get("/api/stack/pipeline", params={"work_dir": work_dir})
    r.raise_for_status()
    return r.json()


def stack_run_step(client: httpx.Client, work_dir: str, step_id: str) -> dict:
    """执行单步。"""
    r = client.post("/api/stack/run-step", json={"work_dir": work_dir, "step_id": step_id}, timeout=7200.0)
    if r.status_code != 200:
        try:
            j = r.json()
            detail = j.get("detail") or j.get("error_message", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(detail if isinstance(detail, str) else str(detail))
    return r.json()


def stack_run_steps(client: httpx.Client, work_dir: str, from_step_index: int) -> dict:
    """从 from_step_index 起执行到结束。"""
    r = client.post(
        "/api/stack/run-steps",
        json={"work_dir": work_dir, "from_step_index": from_step_index},
        timeout=86400.0,
    )
    if r.status_code != 200:
        try:
            j = r.json()
            detail = j.get("detail") or j.get("error_message", r.text)
        except Exception:
            detail = r.text
        raise RuntimeError(detail if isinstance(detail, str) else str(detail))
    return r.json()
