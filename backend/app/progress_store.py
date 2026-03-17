"""
In-memory (or Redis) store for task progress updates; consumed by WebSocket or long-polling.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from shared_models import InSARProgressUpdate

# In production, use Redis; for single-process use a dict keyed by task_id
_USE_REDIS = os.environ.get("INSAR_PROGRESS_REDIS", "").lower() in ("1", "true", "yes")
_storage: Dict[str, List[InSARProgressUpdate]] = {}


def push_progress(task_id: str, progress_pct: float, step_description: str, stage: Optional[str] = None) -> None:
    update = InSARProgressUpdate(
        task_id=task_id,
        progress_pct=progress_pct,
        step_description=step_description,
        stage=stage,
        timestamp_iso=datetime.now(tz=timezone.utc).isoformat(),
    )
    if _USE_REDIS:
        try:
            import redis
            r = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
            key = f"insar:progress:{task_id}"
            r.rpush(key, update.model_dump_json())
            r.expire(key, 86400 * 2)  # 2 days
        except Exception:
            pass
    if task_id not in _storage:
        _storage[task_id] = []
    _storage[task_id].append(update)


def get_progress_list(task_id: str, after_index: int = 0) -> List[InSARProgressUpdate]:
    if _USE_REDIS:
        try:
            import redis
            r = redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
            key = f"insar:progress:{task_id}"
            raw = r.lrange(key, after_index, -1)
            return [InSARProgressUpdate.model_validate_json(b) for b in raw]
        except Exception:
            return []
    return _storage.get(task_id, [])[after_index:]


def get_latest_progress(task_id: str) -> Optional[InSARProgressUpdate]:
    updates = get_progress_list(task_id)
    return updates[-1] if updates else None
