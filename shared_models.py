"""
Shared Pydantic models for InSAR web services.
Used by FastAPI, Celery workers, and frontend contracts.
Path convention: host insar-system/data maps to container /app/data.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ---------- Request: task submission ----------
class InSARTaskRequest(BaseModel):
    """Request payload for starting an InSAR S1 import/registration task."""

    zip_path: str = Field(..., description="Path to Sentinel-1 SAFE zip (under /app/data in container)")
    orbit_dir: str = Field(..., description="Directory containing orbit EOF files")
    dem_path: str = Field(..., description="Path to DEM file (WGS84)")
    aux_dir: str = Field(..., description="Directory for Sentinel-1 aux products (e.g. cal/noise)")
    target_shp_path: Optional[str] = Field(
        None,
        description="Optional path to target.shp for regionOfInterest (SNWE bbox derived from shapefile)",
    )
    bbox_snwe: Optional[list[float]] = Field(
        None,
        description="Optional [South, North, West, East] in degrees (overridden by target_shp if both set)",
    )
    swaths: str = Field(default="1 2 3", description="Swath numbers, e.g. '1 2 3'")
    polarization: str = Field(default="vv", description="Polarization (e.g. vv, vh)")
    output_dir: Optional[str] = Field(
        None,
        description="Output directory for SLC/VRT (default: derived from zip_path)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "zip_path": "/app/data/slc/S1A_IW_SLC__1SDV_20230101.zip",
                "orbit_dir": "/app/data/orbits",
                "dem_path": "/app/data/dem/dem.wgs84",
                "aux_dir": "/app/data/aux",
                "target_shp_path": "/app/data/roi/target.shp",
                "swaths": "1 2 3",
                "polarization": "vv",
            }
        }


# ---------- Progress: real-time updates ----------
class InSARProgressUpdate(BaseModel):
    """Real-time progress update for a running task."""

    task_id: str = Field(..., description="Celery task ID")
    progress_pct: float = Field(..., ge=0.0, le=100.0, description="Progress percentage")
    step_description: str = Field(..., description="Current step description (e.g. from ISCE2 stdout)")
    stage: Optional[str] = Field(None, description="Stage label: unpack_reference, unpack_secondary, etc.")
    timestamp_iso: Optional[str] = Field(None, description="ISO timestamp of update")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc-123",
                "progress_pct": 45.0,
                "step_description": "Extracting swath 2...",
                "stage": "unpack_reference",
            }
        }


# ---------- Result: task completion ----------
class InSARTaskResult(BaseModel):
    """Result returned when an InSAR S1 import/registration task completes."""

    task_id: str = Field(..., description="Celery task ID")
    success: bool = Field(..., description="Whether the task completed successfully")
    slc_vrt_paths: list[str] = Field(
        default_factory=list,
        description="Paths to generated .slc.vrt (or equivalent) files under /app/data",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra metadata (e.g. swath count, reference date, bbox)",
    )
    error_message: Optional[str] = Field(None, description="Error message if success is False")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "abc-123",
                "success": True,
                "slc_vrt_paths": ["/app/data/out/20230101/IW1.slc.vrt", "/app/data/out/20230101/IW2.slc.vrt"],
                "metadata": {"reference_date": "20230101", "swaths": [1, 2]},
            }
        }


# ---------- Stack 流程初始化（topsStack） ----------
class StackConfigRequest(BaseModel):
    """Request for initializing ISCE2 topsStack: generate configs + run_files, then pipeline.json.
    Aligned with stackSentinel.py createParser().
    """

    work_dir: str = Field(..., description="Working directory (configs, run_files, pipeline.json)")
    slc_dir: str = Field(..., description="Directory with Sentinel SLC zips or SAFE (S1*_IW_SLC*)")
    dem_path: str = Field(..., description="Path to DEM file (WGS84)")
    orbit_dir: str = Field(..., description="Directory with orbit files")
    aux_dir: str = Field(..., description="Directory for Sentinel-1 aux (cal/noise)")
    bbox_snwe: Optional[list[float]] = Field(
        None,
        description="[South, North, West, East] in degrees; None = common overlap",
    )
    reference_date: Optional[str] = Field(
        None,
        description="Reference date YYYYMMDD; None = first date",
    )
    workflow: str = Field(
        default="interferogram",
        description="Workflow: slc, correlation, interferogram, offset",
    )
    swaths: str = Field(default="1 2 3", description="Swath numbers, e.g. '1 2 3'")
    polarization: str = Field(default="vv", description="Polarization (e.g. vv, vh)")
    exclude_dates: Optional[str] = Field(None, description="Comma-separated dates to exclude")
    include_dates: Optional[str] = Field(None, description="Comma-separated dates to include")
    start_date: Optional[str] = Field(None, description="Start date YYYY-MM-DD")
    stop_date: Optional[str] = Field(None, description="Stop date YYYY-MM-DD")
    coregistration: str = Field(default="NESD", description="geometry or NESD")
    num_connections: str = Field(default="1", description="Interferogram connections per date")
    num_process: int = Field(default=1, description="Parallel tasks per run step")

    class Config:
        json_schema_extra = {
            "example": {
                "work_dir": "/path/to/processing/stack",
                "slc_dir": "/path/to/radar_zips",
                "dem_path": "/path/to/dem.wgs84",
                "orbit_dir": "/path/to/orbits",
                "aux_dir": "/path/to/aux",
                "bbox_snwe": [29.8, 30.2, 101.8, 102.2],
                "workflow": "interferogram",
                "swaths": "1 2 3",
                "polarization": "vv",
            }
        }


# ---------- 新建工程 ----------
class CreateProjectRequest(BaseModel):
    """前端「定义新工程」提交：在项目路径下创建 {项目名称}.md 工程文件。项目路径必填（用户选择的 Windows 路径）。"""

    name: str = Field(..., min_length=1, description="项目名称")
    radar_type: str = Field(..., min_length=1, description="雷达数据类型，如 Sentinel-1")
    project_path: str = Field(
        ...,
        min_length=1,
        description="项目路径（必填，Windows 下的完整路径；Docker 内由服务端映射，对用户黑箱）",
    )


class CreateProjectResponse(BaseModel):
    """新建工程成功后的返回。project_path / file_path 均为用户侧的 Windows 路径，不暴露容器路径。"""

    id: str = Field(..., description="项目 id（自动生成）")
    name: str = Field(..., description="项目名称")
    radar_type: str = Field(..., description="雷达数据类型")
    project_path: str = Field(..., description="项目完整路径（用户侧路径，工程文件所在目录）")
    created_at: str = Field(..., description="建立时间（ISO 8601）")
    file_path: str = Field(..., description="工程文件路径（用户侧路径，.md 文件）")
