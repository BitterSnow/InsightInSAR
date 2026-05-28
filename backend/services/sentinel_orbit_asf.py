"""
Sentinel-1 精密星历（POEORB）与 ASF S1QC 目录对接：解析 SLC/SAFE 成像时刻，
在轨道目录中查找覆盖该时刻的 EOF；若缺失则从 https://s1qc.asf.alaska.edu/aux_poeorb/ 下载。

不依赖 ISCE2；仅使用标准库 HTTP 与正则。星历文件名中的 V 段为 validity 起止（UTC）。
"""
from __future__ import annotations

import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.services.s1_processing_service import resolve_safe_paths

LOGGER = logging.getLogger(__name__)

ASF_POEORB_BASE = "https://s1qc.asf.alaska.edu/aux_poeorb/"
ASF_POEORB_MIRROR_BASE = "https://s1-orbits.s3.us-west-2.amazonaws.com/AUX_POEORB/"
USER_AGENT = "insar-system-orbit/1.0"

# S1A_OPER_AUX_POEORB_OPOD_<publish>_V<valid_start>_<valid_end>.EOF
_POEORB_VALIDITY_RE = re.compile(
    r"(S1[A-Z])_OPER_AUX_POEORB_OPOD_\d{8}T\d{6}_V(\d{8}T\d{6})_(\d{8}T\d{6})\.EOF",
    re.IGNORECASE,
)

_asf_index_cache: Optional[Tuple[float, List[str]]] = None
ASF_INDEX_CACHE_TTL_SEC = 3600


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_safe_sensing_mission(path: str) -> Optional[Tuple[str, datetime, str]]:
    """
    从 SAFE zip / .SAFE 目录名解析卫星（S1A/S1B/S1C 等）与成像起始时刻（UTC）。
    返回 (mission, sensing_utc, label) ；失败返回 None。
    """
    name = os.path.basename(path.rstrip("/\\"))
    if name.lower().endswith(".zip"):
        name = name[:-4]
    m_mission = re.search(r"(S1[A-Z])", name, re.I)
    if not m_mission:
        return None
    mission = m_mission.group(1).upper()
    times = re.findall(r"(\d{8}T\d{6})", name)
    if not times:
        return None
    try:
        sensing = datetime.strptime(times[0], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    label = name[:80] + ("…" if len(name) > 80 else "")
    return (mission, sensing, label)


def parse_poeorb_validity(filename: str) -> Optional[Tuple[str, datetime, datetime]]:
    """从 POEORB 文件名解析任务代与 validity 起止（UTC）。不匹配则 None。"""
    m = _POEORB_VALIDITY_RE.search(filename.strip())
    if not m:
        return None
    mission = m.group(1).upper()
    try:
        vs = datetime.strptime(m.group(2), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        ve = datetime.strptime(m.group(3), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (mission, vs, ve)


def _poeorb_covers_sensing(filename: str, mission: str, sensing: datetime) -> bool:
    p = parse_poeorb_validity(filename)
    if not p:
        return False
    mis, vs, ve = p
    if mis != mission:
        return False
    st = _utc(sensing)
    return vs <= st <= ve


def list_local_eof_basenames(orbit_dir: str) -> List[str]:
    if not os.path.isdir(orbit_dir):
        return []
    out: List[str] = []
    for n in os.listdir(orbit_dir):
        if n.lower().endswith(".eof"):
            out.append(n)
    return out


def find_covering_poeorb_in_list(
    mission: str,
    sensing: datetime,
    eof_names: List[str],
) -> Optional[str]:
    """在候选 EOF 文件名中选取覆盖 sensing 的 POEORB；多条时取 validity 区间最短者。"""
    st = _utc(sensing)
    best: Optional[Tuple[str, float]] = None
    for name in eof_names:
        p = parse_poeorb_validity(name)
        if not p:
            continue
        mis, vs, ve = p
        if mis != mission or not (vs <= st <= ve):
            continue
        span = (ve - vs).total_seconds()
        if best is None or span < best[1]:
            best = (name, span)
    return best[0] if best else None


def fetch_asf_poeorb_index(force_refresh: bool = False) -> List[str]:
    """
    拉取 ASF aux_poeorb 目录索引，解析出所有 .EOF 文件名（缓存 TTL 默认 1 小时）。
    """
    global _asf_index_cache
    now = time.time()
    if (
        not force_refresh
        and _asf_index_cache is not None
        and now - _asf_index_cache[0] < ASF_INDEX_CACHE_TTL_SEC
    ):
        return list(_asf_index_cache[1])

    req = urllib.request.Request(
        ASF_POEORB_BASE,
        headers={"User-Agent": USER_AGENT},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    # Apache 目录列表: href="FILENAME.EOF"
    names = re.findall(
        r'href="(S1[A-Z]_OPER_AUX_POEORB[^"]+\.EOF)"',
        body,
        flags=re.IGNORECASE,
    )
    if not names:
        names = re.findall(r"(S1[A-Z]_OPER_AUX_POEORB\S+\.EOF)", body, flags=re.IGNORECASE)
    uniq = sorted(set(names))
    if not uniq:
        LOGGER.warning(
            "ASF POEORB index parse returned 0 files (page layout may have changed). Body snippet: %s",
            body[:400].replace("\n", " "),
        )
    _asf_index_cache = (now, uniq)
    LOGGER.info("ASF POEORB index loaded: %d files", len(uniq))
    return list(uniq)


def pick_asf_poeorb_for_scene(
    mission: str,
    sensing: datetime,
    index: Optional[List[str]] = None,
) -> Optional[str]:
    """从 ASF 全量索引中选一个覆盖该景成像时刻的 POEORB 文件名。"""
    names = index if index is not None else fetch_asf_poeorb_index()
    mission = mission.upper()
    # 性能：先按任务代过滤
    cand = [n for n in names if n.upper().startswith(mission + "_OPER_AUX_POEORB")]
    return find_covering_poeorb_in_list(mission, sensing, cand)


def download_poeorb_file(filename: str, dest_dir: str) -> str:
    """
    下载单个 EOF 到 dest_dir，返回本地绝对路径。
    优先 s1qc.asf.alaska.edu；若返回 401/403/404 等，则回退到 ASF 维护的公开 S3 镜像。
    """
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, filename)
    urls = [
        ASF_POEORB_BASE + filename,
        ASF_POEORB_MIRROR_BASE + filename,
    ]
    errs: List[str] = []
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = resp.read()
            with open(dest_path, "wb") as f:
                f.write(data)
            return os.path.abspath(dest_path)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            errs.append(f"{url} -> {e}")
            continue
    raise RuntimeError(" ; ".join(errs))


def ensure_precise_orbits_for_stack(
    slc_dir: str,
    orbit_dir: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    为 Stack 初始化预检：解析 SLC 目录下各 SAFE 成像时刻，确保 orbit_dir 内存在覆盖该时刻的 POEORB；
    缺失时从 ASF 下载。

    Returns:
        ok: bool
        message: 摘要（失败时人类可读）
        scenes: 每景的预检记录
        downloaded: 已下载的文件名列表
        errors: 错误字符串列表
    """
    if (os.environ.get("INSAR_SKIP_ASF_ORBIT_DOWNLOAD") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return {
            "ok": True,
            "message": "已跳过 ASF 轨道下载（INSAR_SKIP_ASF_ORBIT_DOWNLOAD）",
            "scenes": [],
            "downloaded": [],
            "errors": [],
        }

    safe_paths = resolve_safe_paths(slc_dir)
    if not safe_paths:
        return {
            "ok": False,
            "message": f"SLC 目录下未找到 .zip 或 .SAFE：{slc_dir}",
            "scenes": [],
            "downloaded": [],
            "errors": [f"无 SAFE 数据: {slc_dir}"],
        }

    orbit_dir = os.path.abspath(orbit_dir)
    os.makedirs(orbit_dir, exist_ok=True)
    local_names = list_local_eof_basenames(orbit_dir)

    scenes_out: List[Dict[str, Any]] = []
    downloaded: List[str] = []
    errors: List[str] = []

    # 先构建本地覆盖关系，减少重复下载
    index: Optional[List[str]] = None

    for safe_path in safe_paths:
        parsed = parse_safe_sensing_mission(safe_path)
        if not parsed:
            err = f"无法从文件名解析成像时刻：{os.path.basename(safe_path)}"
            errors.append(err)
            scenes_out.append(
                {
                    "safe": os.path.basename(safe_path),
                    "ok": False,
                    "detail": err,
                }
            )
            continue

        mission, sensing, label = parsed
        st_iso = sensing.strftime("%Y-%m-%dT%H:%M:%SZ")

        cover_local = find_covering_poeorb_in_list(mission, sensing, local_names)
        if cover_local:
            scenes_out.append(
                {
                    "safe": label,
                    "mission": mission,
                    "sensing_utc": st_iso,
                    "status": "local",
                    "eof_file": cover_local,
                }
            )
            continue

        if progress_callback:
            progress_callback(1.0, f"检索 ASF 精密星历目录…（{mission} {st_iso}）")

        try:
            if index is None:
                index = fetch_asf_poeorb_index()
            asf_name = pick_asf_poeorb_for_scene(mission, sensing, index)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            msg = f"无法访问 ASF 星历目录 ({ASF_POEORB_BASE}): {e}"
            errors.append(msg)
            return {
                "ok": False,
                "message": msg,
                "scenes": scenes_out,
                "downloaded": downloaded,
                "errors": errors,
            }

        if not asf_name:
            msg = (
                f"未在 ASF 找到覆盖成像时刻 {st_iso} 的 {mission} 精密星历（POEORB）。"
                " 可能尚未发布，请数日后再试或使用 RESTITUTED 星历。"
            )
            errors.append(msg)
            scenes_out.append(
                {
                    "safe": label,
                    "mission": mission,
                    "sensing_utc": st_iso,
                    "status": "not_found_asf",
                    "detail": msg,
                }
            )
            continue

        if progress_callback:
            progress_callback(2.0, f"下载精密星历: {asf_name}")

        try:
            download_poeorb_file(asf_name, orbit_dir)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            msg = f"下载失败 {asf_name}: {e}"
            errors.append(msg)
            scenes_out.append(
                {
                    "safe": label,
                    "mission": mission,
                    "sensing_utc": st_iso,
                    "status": "download_fail",
                    "expected_file": asf_name,
                    "detail": msg,
                }
            )
            continue

        downloaded.append(asf_name)
        local_names.append(asf_name)
        scenes_out.append(
            {
                "safe": label,
                "mission": mission,
                "sensing_utc": st_iso,
                "status": "downloaded",
                "eof_file": asf_name,
            }
        )

    # 任一景解析失败、找不到星历或下载失败则整体失败
    fatal = any(
        isinstance(s, dict)
        and (
            s.get("status") in ("not_found_asf", "download_fail")
            or s.get("ok") is False
        )
        for s in scenes_out
    )
    ok = not fatal
    if not scenes_out:
        msg = "未产生任何星历预检记录"
    elif ok:
        msg = (
            f"轨道目录已就绪（{orbit_dir}）"
            + (f"，新下载 {len(downloaded)} 个 EOF" if downloaded else "")
        )
    else:
        msg = "精密星历预检未全部通过，详见 scenes / errors"

    return {
        "ok": ok,
        "message": msg,
        "scenes": scenes_out,
        "downloaded": downloaded,
        "errors": errors,
        "asf_base_url": ASF_POEORB_BASE,
    }


def format_orbit_preflight_for_ui(pref: Dict[str, Any]) -> str:
    """格式化为日志/弹窗用多行文本。"""
    lines: List[str] = []
    lines.append(pref.get("message", ""))
    base = pref.get("asf_base_url") or ASF_POEORB_BASE
    lines.append(f"ASF 精密星历目录: {base}")
    for s in pref.get("scenes") or []:
        if not isinstance(s, dict):
            continue
        if s.get("status") == "local":
            lines.append(f"  [已有] {s.get('safe')} → {s.get('eof_file')}")
        elif s.get("status") == "downloaded":
            lines.append(f"  [已下载] {s.get('safe')} → {s.get('eof_file')}")
        else:
            lines.append(
                f"  [异常] {s.get('safe', '')} {s.get('sensing_utc', '')} — {s.get('detail', s)}"
            )
    for e in pref.get("errors") or []:
        lines.append(f"  错误: {e}")
    dl = pref.get("downloaded") or []
    if dl:
        lines.append("已下载文件: " + ", ".join(dl))
    return "\n".join(lines)
