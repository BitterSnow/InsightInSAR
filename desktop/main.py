#!/usr/bin/env python3
"""
InSAR 桌面端入口。
使用 PySide6 构建，与后端 FastAPI 通过 HTTP 通信；支持原生文件夹选择与本地大栅格显示。
界面使用 qt-material 深色主题（Material Design 风格）。
打包版（PyInstaller 冻结）：以 exe 所在目录为应用根，默认 WSL 模式，并从 wsl_config.env 加载配置。
"""
import os
import sys
from pathlib import Path


def _is_frozen() -> bool:
    """是否以 PyInstaller 等冻结方式运行。"""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _get_app_root() -> Path:
    """应用根目录：冻结时为 exe 所在目录，否则为项目根（desktop 的上级）。"""
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _get_wsl_config_candidates(app_root: Path) -> list[Path]:
    """
    按优先级列出 wsl_config.env 的查找路径（与 exe 位置解耦，移动 Desktop 后仍能找到）。
    1) 固定用户路径（%LOCALAPPDATA%\\InSAR\\wsl_config.env）— 向导与 Desktop 共用，与安装路径无关
    2) exe/项目根下的 wsl_config.env
    3) 打包版：父目录、兄弟目录（兼容旧部署）
    """
    candidates: list[Path] = []
    try:
        from wsl_config_path import get_wsl_config_path
        p = get_wsl_config_path()
        if p is not None:
            candidates.append(p)
    except Exception:
        pass
    candidates.append(app_root / "wsl_config.env")
    if _is_frozen():
        parent = app_root.parent
        candidates.append(parent / "wsl_config.env")
        candidates.append(parent / "InSAR WSL Deploy Wizard" / "wsl_config.env")
        candidates.append(parent / "InSAR WSL 部署向导" / "wsl_config.env")
    return candidates


def _load_wsl_config(app_root: Path) -> None:
    """从 wsl_config.env 加载 WSL 相关环境变量（优先固定用户路径，与 exe 安装位置无关）。"""
    for cfg in _get_wsl_config_candidates(app_root):
        if not cfg.is_file():
            continue
        try:
            for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k:
                        os.environ.setdefault(k, v)
            return
        except Exception:
            continue


# 应用根与 sys.path
PROJECT_ROOT = _get_app_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["INSAR_PROJECT_ROOT"] = str(PROJECT_ROOT)
try:
    from backend.services.wsl_runner import bootstrap_isce2_main_env, load_wsl_config_env

    load_wsl_config_env(str(PROJECT_ROOT))
    bootstrap_isce2_main_env()
except Exception:
    pass
if _is_frozen():
    os.environ.setdefault("INSAR_USE_WSL", "1")
    _load_wsl_config(PROJECT_ROOT)
else:
    # 源码运行（含 scripts/start_desktop_wsl.bat 启动）：确保 WSL 模式与配置生效，避免子进程未继承导致初始化报错
    os.environ.setdefault("INSAR_USE_WSL", "1")
    _load_wsl_config(PROJECT_ROOT)

# 将运行期错误写入 logs/desktop.log。打包 exe 在客户机可能安装于不可写目录，故冻结运行时优先使用 %LOCALAPPDATA%\InSAR\logs，确保有错误记录。
import logging
import sys

def _desktop_log_candidates():
    yield PROJECT_ROOT / "logs" / "desktop.log"
    if _is_frozen():
        local_app_data = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or ""
        if local_app_data:
            yield Path(local_app_data) / "InSAR" / "logs" / "desktop.log"

# UTF-8 BOM，便于 Windows 记事本等按 UTF-8 打开，避免中文乱码
_UTF8_BOM = b"\xef\xbb\xbf"

def _ensure_log_file_utf8_bom(path: Path) -> None:
    """若日志文件为空或不存在，写入 UTF-8 BOM，确保以 UTF-8 打开时中文不乱码。"""
    try:
        if not path.exists() or path.stat().st_size == 0:
            path.write_bytes(_UTF8_BOM)
        else:
            head = path.read_bytes()[:3]
            if head != _UTF8_BOM:
                # 已有内容但无 BOM：在文件头插入 BOM（旧文件可能被误读为 GBK，新写入统一 UTF-8）
                body = path.read_bytes()
                path.write_bytes(_UTF8_BOM + body)
    except (OSError, PermissionError):
        pass

_root_logger = logging.getLogger()
_root_logger.setLevel(logging.DEBUG)
_log_file = None
_file_handler = None
for _log_file in _desktop_log_candidates():
    _log_dir = _log_file.parent
    try:
        _log_dir.mkdir(parents=True, exist_ok=True)
        _ensure_log_file_utf8_bom(_log_file)
        _file_handler = logging.FileHandler(_log_file, mode="a", encoding="utf-8")
        _file_handler.setLevel(logging.DEBUG)
        _file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        _root_logger.addHandler(_file_handler)
        _root_logger.info("Desktop log file: %s", _log_file)
        break
    except (OSError, PermissionError) as _e:
        _file_handler = None
        continue
if _file_handler is None:
    # 所有候选路径均无法写入时，用 stderr 兜底（通过 bat 启动时 2>&1 仍会进入 logs/desktop.log）
    _fallback = logging.StreamHandler(sys.stderr)
    _fallback.setLevel(logging.WARNING)
    _fallback.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    _root_logger.addHandler(_fallback)
    _root_logger.warning("无法写入日志文件（已尝试 %s），错误将输出到 stderr。", _log_file or "logs/desktop.log")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# 从项目根运行 (python -m desktop.main) 时 desktop 为包；从 desktop/ 运行则用 app
try:
    from desktop.app.main_window import MainWindow
except ModuleNotFoundError:
    from app.main_window import MainWindow


def _maybe_prompt_wsl_wizard(win: "QWidget") -> None:
    """打包版且 WSL 模式未配置时，提示用户运行部署向导（可选打开向导 exe）。"""
    if not _is_frozen():
        return
    try:
        from backend.services import wsl_runner
        if not wsl_runner.use_wsl():
            return
        if wsl_runner.get_wsl_project_root():
            return
    except Exception:
        return
    import subprocess
    from PySide6.QtWidgets import QMessageBox
    # 向导 exe 查找顺序：同目录 → 兄弟目录 → PATH（与 exe 安装路径解耦）
    wizard_exe = None
    for candidate in [
        PROJECT_ROOT / "InSAR WSL Deploy Wizard.exe",
        PROJECT_ROOT / "InSAR WSL 部署向导.exe",
        PROJECT_ROOT.parent / "InSAR WSL Deploy Wizard" / "InSAR WSL Deploy Wizard.exe",
        PROJECT_ROOT.parent / "InSAR WSL 部署向导" / "InSAR WSL Deploy Wizard.exe",
    ]:
        if candidate.is_file():
            wizard_exe = candidate
            break
    if wizard_exe is None:
        try:
            which = subprocess.run(
                ["where", "InSAR WSL Deploy Wizard.exe"],
                capture_output=True,
                text=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if which.returncode == 0 and which.stdout.strip():
                wizard_exe = Path(which.stdout.strip().splitlines()[0].strip())
        except Exception:
            pass
    msg = "WSL 处理环境未配置。请先运行「InSAR WSL 部署向导」导入 WSL 镜像并写入配置（配置会保存到本机固定位置，与 Desktop 安装路径无关）。"
    mb = QMessageBox(win)
    mb.setWindowTitle("WSL 未配置")
    mb.setText(msg)
    mb.setIcon(QMessageBox.Icon.Information)
    open_btn = None
    if wizard_exe is not None and wizard_exe.is_file():
        open_btn = mb.addButton("打开向导", QMessageBox.ButtonRole.ActionRole)
    mb.addButton(QMessageBox.StandardButton.Ok)
    mb.exec()
    if open_btn and mb.clickedButton() == open_btn:
        try:
            subprocess.Popen(
                [str(wizard_exe)],
                cwd=str(PROJECT_ROOT),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("InSAR Desktop")

    # qt-material：须在 PySide6 已 import 后使用
    from qt_material import apply_stylesheet
    apply_stylesheet(app, theme="dark_teal.xml")

    win = MainWindow()
    win.show()
    if _is_frozen():
        _maybe_prompt_wsl_wizard(win)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
