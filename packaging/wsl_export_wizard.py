#!/usr/bin/env python3
"""
InSAR WSL 导出向导：选择本机 WSL 发行版并导出为 TAR 镜像。
用法：python -m packaging.wsl_export_wizard
  或从安装目录双击运行（打包为 exe）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# 支持从项目根或 packaging 目录运行
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _get_app_root(parsed_app_root: str | None) -> Path:
    if parsed_app_root and Path(parsed_app_root).is_dir():
        return Path(parsed_app_root).resolve()
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return _REPO_ROOT


def _subprocess_creationflags() -> int:
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def _decode_subprocess_output(data: bytes | None) -> str:
    if not data:
        return ""
    if b"\x00" in data:
        for enc in ("utf-16-le", "utf-16"):
            try:
                return data.decode(enc, errors="strict").strip()
            except (UnicodeDecodeError, LookupError):
                pass

    for enc in ("utf-8-sig", "utf-8", "mbcs", "gbk", "cp936", "latin-1"):
        try:
            return data.decode(enc, errors="strict").strip()
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace").strip()


def _resource_path(app_root: Path, filename: str) -> Path:
    p1 = (app_root / filename).resolve()
    if p1.is_file():
        return p1
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p2 = (Path(meipass) / filename).resolve()
        if p2.is_file():
            return p2
    return (Path(__file__).resolve().parent / filename).resolve()


def check_wsl_available() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True,
            timeout=15,
            creationflags=_subprocess_creationflags(),
        )
        if r.returncode != 0:
            return False, "WSL 未正确安装或未启用。"
        return True, "WSL 可用"
    except FileNotFoundError:
        return False, "未找到 wsl 命令，请先安装 WSL。"
    except Exception as e:
        return False, str(e)


def list_wsl_distros() -> tuple[bool, list[str], str]:
    try:
        r = subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True,
            timeout=15,
            creationflags=_subprocess_creationflags(),
        )
        if r.returncode != 0:
            err = _decode_subprocess_output(r.stderr) or _decode_subprocess_output(r.stdout) or "列出发行版失败"
            return False, [], err
        raw = _decode_subprocess_output(r.stdout)
        distros = [cleaned for line in raw.splitlines() if (cleaned := line.strip().replace("\x00", ""))]
        return True, distros, ""
    except Exception as e:
        return False, [], str(e)


def run_export(distro: str, tar_path: str) -> tuple[bool, str]:
    target = Path(tar_path).resolve()
    if not distro.strip():
        return False, "发行版名称不能为空。"
    if target.suffix.lower() != ".tar":
        return False, "导出文件必须是 .tar。"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            ["wsl", "--export", distro, str(target)],
            capture_output=True,
            timeout=3600,
            creationflags=_subprocess_creationflags(),
        )
        if r.returncode != 0:
            err = _decode_subprocess_output(r.stderr) or _decode_subprocess_output(r.stdout) or "导出失败"
            return False, err
        if not target.is_file():
            return False, "导出命令执行成功，但未检测到目标文件。"
        return True, f"导出成功：{target}"
    except subprocess.TimeoutExpired:
        return False, "导出超时（超过 60 分钟）。"
    except Exception as e:
        return False, str(e)


def main_ui(app_root: Path) -> None:
    from PySide6.QtCore import QThread, Signal
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import (
        QApplication,
        QFileDialog,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QComboBox,
        QVBoxLayout,
        QWidget,
    )

    class ExportWorker(QThread):
        finished_signal = Signal(bool, str)

        def __init__(self, distro: str, tar_path: str):
            super().__init__()
            self.distro = distro
            self.tar_path = tar_path

        def run(self) -> None:
            ok, msg = run_export(self.distro, self.tar_path)
            self.finished_signal.emit(ok, msg)

    app = QApplication(sys.argv)
    app.setApplicationName("InSAR WSL 导出向导")

    win = QWidget()
    win.setWindowTitle("InSAR WSL 导出向导")
    icon_path = _resource_path(app_root, "wizard_icon.ico")
    if icon_path.is_file():
        icon = QIcon(str(icon_path))
        app.setWindowIcon(icon)
        win.setWindowIcon(icon)
    win.setMinimumWidth(560)

    layout = QVBoxLayout(win)

    grp_root = QGroupBox("应用根目录")
    form_root = QFormLayout(grp_root)
    root_edit = QLineEdit()
    root_edit.setReadOnly(True)
    root_edit.setText(str(app_root))
    form_root.addRow("路径：", root_edit)
    layout.addWidget(grp_root)

    grp1 = QGroupBox("1. 选择要打包的 WSL 发行版")
    ly1 = QHBoxLayout(grp1)
    distro_combo = QComboBox()
    distro_combo.setEditable(False)
    btn_refresh = QPushButton("刷新列表")
    ly1.addWidget(distro_combo, 1)
    ly1.addWidget(btn_refresh)
    layout.addWidget(grp1)

    grp2 = QGroupBox("2. 选择导出文件位置（.tar）")
    ly2 = QHBoxLayout(grp2)
    tar_edit = QLineEdit()
    tar_edit.setPlaceholderText("例如 D:\\WSL\\insar-wsl.tar")
    browse_tar = QPushButton("浏览…")

    def pick_tar() -> None:
        path, _ = QFileDialog.getSaveFileName(
            win,
            "选择导出文件",
            str(app_root / "insar-wsl.tar"),
            "TAR 文件 (*.tar);;全部 (*)",
        )
        if path:
            if not path.lower().endswith(".tar"):
                path = f"{path}.tar"
            tar_edit.setText(path)

    browse_tar.clicked.connect(pick_tar)
    ly2.addWidget(tar_edit)
    ly2.addWidget(browse_tar)
    layout.addWidget(grp2)

    progress = QProgressBar()
    progress.setVisible(False)
    layout.addWidget(progress)

    status = QLabel("")
    status.setWordWrap(True)
    layout.addWidget(status)

    def refresh_distros() -> None:
        ok, msg = check_wsl_available()
        distro_combo.clear()
        if not ok:
            status.setText("⚠ " + msg)
            return
        ok_list, distros, err = list_wsl_distros()
        if not ok_list:
            status.setText("⚠ 无法读取发行版列表：" + err)
            return
        if not distros:
            status.setText("⚠ 当前没有可导出的 WSL 发行版。")
            return
        distro_combo.addItems(distros)
        default_tar = app_root / "insar-wsl.tar"
        if not tar_edit.text().strip():
            tar_edit.setText(str(default_tar))
        status.setText("✓ 已读取发行版列表。请选择发行版和导出位置，然后点击执行导出。")

    def on_export_finished(ok: bool, msg: str) -> None:
        progress.setVisible(False)
        btn_export.setEnabled(True)
        win._export_worker = None
        if not ok:
            status.setText("导出失败：" + msg)
            QMessageBox.warning(win, "导出失败", msg)
            return
        status.setText(msg)
        QMessageBox.information(win, "完成", msg)

    def do_export() -> None:
        distro = distro_combo.currentText().strip()
        tar_path = tar_edit.text().strip()
        if not distro:
            status.setText("请选择一个 WSL 发行版。")
            return
        if not tar_path:
            status.setText("请选择导出文件路径。")
            return
        if getattr(win, "_export_worker", None) and win._export_worker.isRunning():
            return
        btn_export.setEnabled(False)
        progress.setVisible(True)
        progress.setRange(0, 0)
        status.setText("正在导出 WSL 镜像（可能需要数分钟，请勿关闭窗口）…")
        worker = ExportWorker(distro, tar_path)
        worker.finished_signal.connect(on_export_finished)
        win._export_worker = worker
        worker.start()

    btn_export = QPushButton("执行导出")
    btn_export.clicked.connect(do_export)
    layout.addWidget(btn_export)

    btn_refresh.clicked.connect(refresh_distros)
    refresh_distros()

    win.show()
    sys.exit(app.exec())


def main() -> None:
    parser = argparse.ArgumentParser(description="InSAR WSL 导出向导")
    parser.add_argument("--app-root", type=str, help="应用根目录（默认项目根或 exe 所在目录）")
    args = parser.parse_args()
    app_root = _get_app_root(args.app_root)
    main_ui(app_root)


if __name__ == "__main__":
    main()
