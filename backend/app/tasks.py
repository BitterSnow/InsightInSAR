"""
Celery tasks for InSAR: S1 import/registration with progress reporting.
Parses ISCE2 stdout and pushes InSARProgressUpdate via progress_store.
"""
from __future__ import annotations

import io
import re
import sys
from typing import Optional

from backend.app.celery_app import app
from backend.app.progress_store import push_progress
from shared_models import InSARTaskRequest, InSARTaskResult

# Optional: capture ISCE2 print output to parse progress
_ISCE_PROGRESS_PATTERNS = [
    (re.compile(r"swath\s*[(\d)]+", re.I), "Processing swath"),
    (re.compile(r"extract", re.I), "Extracting image"),
    (re.compile(r"parse", re.I), "Parsing metadata"),
    (re.compile(r"burst", re.I), "Processing burst"),
    (re.compile(r"(\d+)\s*%", re.I), None),  # "45 %" -> use as pct
]


def _parse_stdout_line(line: str) -> Optional[tuple[float, str]]:
    """Try to derive (progress_pct, step_description) from a line of ISCE2 stdout."""
    line = line.strip()
    if not line:
        return None
    pct = None
    for pat, label in _ISCE_PROGRESS_PATTERNS:
        m = pat.search(line)
        if m:
            if label:
                return (None, label + ": " + line[:80])
            if m.lastindex and m.group(1).isdigit():
                pct = float(m.group(1))
                return (pct, line[:80])
            return (None, line[:80])
    return (None, line[:80])


class StdoutCapture:
    """Context manager that captures stdout and forwards parsed progress to push_progress."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        self._prev_stdout: Optional[io.TextIOBase] = None
        self._buffer = io.StringIO()
        self._last_pct = 0.0

    def __enter__(self) -> StdoutCapture:
        self._prev_stdout = sys.stdout
        sys.stdout = self
        return self

    def __exit__(self, *args: object) -> None:
        sys.stdout = self._prev_stdout or sys.stdout

    def write(self, data: str) -> int:
        if self._prev_stdout:
            self._prev_stdout.write(data)
        self._buffer.write(data)
        for line in data.splitlines():
            parsed = _parse_stdout_line(line)
            if parsed:
                pct, desc = parsed
                if pct is not None:
                    self._last_pct = min(100.0, max(0.0, pct))
                    push_progress(self.task_id, self._last_pct, desc, stage="isce_stdout")
                else:
                    push_progress(self.task_id, self._last_pct, desc, stage="isce_stdout")
        return len(data)

    def flush(self) -> None:
        if self._prev_stdout:
            self._prev_stdout.flush()
        self._buffer.flush()


@app.task(bind=True, name="insar.s1_import")
def run_s1_import_task(self, request_dict: dict) -> dict:
    """
    Celery task: run S1 import/registration from InSARTaskRequest (as dict).
    Updates progress via progress_store; returns InSARTaskResult as dict.
    """
    task_id = self.request.id
    request = InSARTaskRequest.model_validate(request_dict)

    def progress_cb(pct: float, msg: str) -> None:
        push_progress(task_id, pct, msg, stage="s1_extract")

    push_progress(task_id, 0.0, "Starting S1 import...", stage="start")
    try:
        # Run with stdout capture so ISCE2 print() can drive progress
        from backend.services.s1_processing_service import run_s1_import_from_request

        with StdoutCapture(task_id):
            result = run_s1_import_from_request(request, progress_callback=progress_cb)
    except Exception as e:
        push_progress(task_id, 0.0, str(e), stage="error")
        return InSARTaskResult(
            task_id=task_id,
            success=False,
            slc_vrt_paths=[],
            metadata={},
            error_message=str(e),
        ).model_dump()

    push_progress(task_id, 100.0, "Task finished.", stage="done")
    return InSARTaskResult(
        task_id=task_id,
        success=result.get("success", False),
        slc_vrt_paths=result.get("slc_vrt_paths", []),
        metadata=result.get("metadata", {}),
        error_message=result.get("error_message"),
    ).model_dump()
