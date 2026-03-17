"""
FastAPI application: task submission, status, and progress.
Long-running work runs in Celery; progress is stored and exposed via API.
"""
import os
import re
import uuid
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import List, Optional

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from shared_models import (
    InSARTaskRequest,
    InSARProgressUpdate,
    InSARTaskResult,
    CreateProjectRequest,
    CreateProjectResponse,
    StackConfigRequest,
)

# Import after app so celery is not required at import time for docs
def _get_celery_task():
    from backend.app.tasks import run_s1_import_task
    return run_s1_import_task

def _get_progress_store():
    from backend.app.progress_store import get_progress_list, get_latest_progress
    return get_progress_list, get_latest_progress


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="InSAR S1 Import API",
    description="Submit and monitor Sentinel-1 TOPS import/registration (ISCE2, no XML).",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/tasks/s1-import", response_model=dict)
def submit_s1_import(request: InSARTaskRequest) -> dict:
    """
    Submit an InSAR S1 import/registration task. Returns task_id for status polling.
    Paths must be valid inside the container (e.g. /app/data/...).
    """
    run_s1_import_task = _get_celery_task()
    task = run_s1_import_task.delay(request.model_dump())
    return {"task_id": task.id, "status": "submitted"}


@app.get("/api/tasks/{task_id}/status")
def get_task_status(task_id: str) -> dict:
    """Get Celery task state and result (when ready)."""
    from celery.result import AsyncResult
    from backend.app.celery_app import app as celery_app

    ar = AsyncResult(task_id, app=celery_app)
    out = {"task_id": task_id, "state": ar.state}
    if ar.ready():
        if ar.successful():
            out["result"] = ar.get()
        else:
            out["error"] = str(ar.result) if ar.result else "Task failed"
    return out


@app.get("/api/tasks/{task_id}/progress", response_model=List[InSARProgressUpdate])
def get_task_progress(task_id: str, after: int = 0) -> List[InSARProgressUpdate]:
    """Get progress updates (for progress bar / log viewer). after=index for long-polling."""
    get_progress_list, _ = _get_progress_store()
    return get_progress_list(task_id, after_index=after)


@app.get("/api/tasks/{task_id}/progress/latest", response_model=Optional[InSARProgressUpdate])
def get_task_progress_latest(task_id: str):
    """Get latest single progress update."""
    _, get_latest = _get_progress_store()
    return get_latest(task_id)


# 当前项目路径：用于「按项目启动 Docker」时挂载。存于项目根目录 .insar_current_project
INSAR_PROJECT_ROOT = os.environ.get("INSAR_PROJECT_ROOT", os.getcwd())
CURRENT_PROJECT_FILE = os.path.join(os.path.abspath(INSAR_PROJECT_ROOT), ".insar_current_project")

# 数据目录浏览与新建工程
DATA_ROOT = os.environ.get("INSAR_DATA_ROOT", "/app/data")


def _is_windows_absolute_path(raw_slash: str) -> bool:
    """是否为 Windows 绝对路径（盘符 + 冒号 + 反斜杠，如 D:/ 或 D:\\）。"""
    if len(raw_slash) >= 2 and raw_slash[1] == ":" and raw_slash[0].isalpha():
        return True
    return False


def _resolve_project_base_dir_and_user_path(project_path: str, _data_root: str) -> tuple[str, str]:
    """
    仅支持在任意目录建项目：用户必须传入 Windows 绝对路径（如 D:\\文件夹\\项目名）。
    非 Windows 绝对路径时返回 400 并提示。
    返回：(actual_base_dir, user_facing_path)
    """
    raw = project_path.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="请指定项目路径")
    raw_slash = raw.replace("\\", "/")
    user_facing = raw.rstrip("/\\")
    if ".." in raw_slash:
        raise HTTPException(status_code=403, detail="项目路径不允许包含 ..")

    if not _is_windows_absolute_path(raw_slash):
        raise HTTPException(
            status_code=400,
            detail="请指定 Windows 绝对路径（例如：D:\\文件夹\\项目名）",
        )

    base_dir = os.path.normpath(raw_slash.replace("/", os.sep))
    return base_dir, user_facing


def _safe_md_filename(name: str) -> str:
    """生成可用于 .md 文件名的安全字符串。"""
    s = re.sub(r'[<>:"/\\|?*]', "_", name.strip())
    return s[:200] if s else "project"


@app.post("/api/projects", response_model=CreateProjectResponse)
def create_project(request: CreateProjectRequest) -> CreateProjectResponse:
    """
    新建工程：在项目路径下创建 {项目名称}.md 文件。
    仅支持 Windows 绝对路径（如 D:\\文件夹\\项目名），非绝对路径将返回 400。
    """
    base_dir, user_facing_path = _resolve_project_base_dir_and_user_path(
        request.project_path, DATA_ROOT
    )
    try:
        os.makedirs(base_dir, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"无法创建目录: {e}")

    project_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    safe_name = _safe_md_filename(request.name)
    file_name = f"{safe_name}.md"
    container_file_path = os.path.join(base_dir, file_name)
    # 返回给用户的文件路径（Windows 侧，不暴露容器路径）
    sep = "\\" if "\\" in user_facing_path else "/"
    user_facing_file_path = user_facing_path.rstrip("/\\") + sep + file_name

    content = f"""# 项目名称
{request.name}

# 项目id
{project_id}

# 雷达数据类型
{request.radar_type}

# 建立时间
{created_at}

# 项目完整路径
{user_facing_path}
"""

    try:
        with open(container_file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"无法写入工程文件: {e}")

    try:
        _write_current_project_path(user_facing_path)
    except HTTPException:
        raise
    except Exception:
        pass

    return CreateProjectResponse(
        id=project_id,
        name=request.name,
        radar_type=request.radar_type,
        project_path=user_facing_path,
        created_at=created_at,
        file_path=user_facing_file_path,
    )


@app.get("/api/data/browse")
def browse_data(path: str = "") -> dict:
    """
    列出 path 下的目录项。path 为空时使用 /app/data；可为相对路径(slc)或绝对路径(/app/data/slc)。
    仅允许访问 DATA_ROOT 下的路径，返回 { path, entries: [{ name, type: 'dir'|'file' }] }。
    """
    base = os.path.normpath(DATA_ROOT)
    if path:
        raw = path.strip().replace("\\", "/")
        if raw.startswith(base) or raw.startswith("/app/data"):
            target = os.path.normpath(raw)
        else:
            target = os.path.normpath(os.path.join(base, raw.lstrip("/")))
    else:
        target = base
    if not target.startswith(base) or ".." in (path or ""):
        raise HTTPException(status_code=403, detail="Path not allowed")
    if not os.path.isdir(target):
        raise HTTPException(status_code=404, detail="Not a directory")
    entries: List[dict] = []
    try:
        for name in sorted(os.listdir(target)):
            full = os.path.join(target, name)
            entries.append({
                "name": name,
                "type": "dir" if os.path.isdir(full) else "file",
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    return {"path": target, "entries": entries}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ---------- 当前项目路径（用于按项目启动 Docker 时挂载 /app/project） ----------
class CurrentProjectResponse(BaseModel):
    project_path: str


class CurrentProjectUpdate(BaseModel):
    project_path: str


def _read_current_project_path() -> str | None:
    try:
        if os.path.isfile(CURRENT_PROJECT_FILE):
            with open(CURRENT_PROJECT_FILE, "r", encoding="utf-8") as f:
                return f.read().strip() or None
    except OSError:
        pass
    return None


def _write_current_project_path(path: str) -> None:
    path = path.strip()
    if not path:
        raise HTTPException(status_code=400, detail="project_path 不能为空")
    try:
        with open(CURRENT_PROJECT_FILE, "w", encoding="utf-8") as f:
            f.write(path)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"无法写入配置: {e}")


@app.get("/api/config/current-project", response_model=CurrentProjectResponse)
def get_current_project():
    """获取当前项目路径（供启动 Docker 脚本读取，挂载为 /app/project）。"""
    path = _read_current_project_path()
    if not path:
        raise HTTPException(status_code=404, detail="尚未设置当前项目路径")
    return CurrentProjectResponse(project_path=path)


@app.put("/api/config/current-project", response_model=CurrentProjectResponse)
def set_current_project(body: CurrentProjectUpdate):
    """设置当前项目路径（新建或切换项目后调用，便于用该路径启动/重启 Docker）。"""
    _write_current_project_path(body.project_path)
    return CurrentProjectResponse(project_path=body.project_path.strip())


# ---------- Stack 流程（topsStack：初始化 + 步骤执行，仅 Python 子进程，无 bash） ----------
def _get_stack_service():
    from backend.services.stack_processing_service import (
        stack_init as _stack_init,
        parse_run_files_to_pipeline,
        load_pipeline,
        run_stack_step,
        run_stack_steps,
    )
    return _stack_init, parse_run_files_to_pipeline, load_pipeline, run_stack_step, run_stack_steps


class StackRunStepRequest(BaseModel):
    work_dir: str
    step_id: str


class StackRunStepsRequest(BaseModel):
    work_dir: str
    from_step_index: int


@app.post("/api/stack/init")
def api_stack_init(request: StackConfigRequest) -> dict:
    """
    初始化 Stack：运行 stackSentinel.py 生成 configs + run_files，解析生成 pipeline.json。
    同步阻塞，适合在桌面 QThread 中调用。
    """
    stack_init_fn, _, _, _, _ = _get_stack_service()
    result = stack_init_fn(request, progress_callback=None)
    return result


@app.get("/api/stack/pipeline")
def api_stack_pipeline(work_dir: str) -> dict:
    """读取 work_dir 下的 pipeline.json；不存在则 404。"""
    _, _, load_pipeline_fn, _, _ = _get_stack_service()
    pipeline = load_pipeline_fn(work_dir)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="未找到 pipeline.json")
    return pipeline


@app.post("/api/stack/run-step")
def api_stack_run_step(body: StackRunStepRequest) -> dict:
    """执行单步（子进程 Python SentinelWrapper.py -c config，无 shell）。"""
    _, _, _, run_step_fn, _ = _get_stack_service()
    return run_step_fn(body.work_dir, body.step_id, progress_callback=None)


@app.post("/api/stack/run-steps")
def api_stack_run_steps(body: StackRunStepsRequest) -> dict:
    """从 from_step_index 起顺序执行到结束。"""
    _, _, _, _, run_steps_fn = _get_stack_service()
    return run_steps_fn(body.work_dir, body.from_step_index, progress_callback=None)
