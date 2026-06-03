#!/usr/bin/env python3
"""
InSAR WSL 部署向导：离线导入预导出的 WSL 镜像并写入 wsl_config.env，供 Desktop 启动时加载。
用法：python -m packaging.wsl_deploy_wizard [--app-root PATH]
  或从安装目录双击运行（打包为 exe 时与 InSAR Desktop.exe 同目录）。
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

# 支持从项目根或 packaging 目录运行
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 固定发行版名，与文档一致
WSL_DISTRO_NAME = "InsarUbuntu24"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def _get_app_root(parsed_app_root: str | None) -> Path:
    if parsed_app_root and Path(parsed_app_root).is_dir():
        return Path(parsed_app_root).resolve()
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return _REPO_ROOT


def _code_install_root(app_root: Path) -> Path:
    """WSL 代码根：优先 exe 同目录（交付版 backend 在 InSAR Desktop 内），否则上一级。"""
    marker = app_root / "backend" / "scripts" / "run_mintpy_init_wsl.py"
    if marker.is_file():
        return app_root
    return app_root.parent


def _subprocess_creationflags() -> int:
    """Windows 下隐藏子进程控制台窗口，避免黑色 wsl 窗口无内容。"""
    if sys.platform == "win32":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return 0


def _decode_subprocess_output(data: bytes | None) -> str:
    """将 subprocess 输出的 bytes 解码为 str，避免 Windows 下 wsl 输出 GBK 导致乱码。"""
    if not data:
        return ""
    # Heuristic: WSL/Windows tools occasionally output UTF-16LE (NUL bytes).
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
    """
    Resolve resource path for both source-run and PyInstaller-frozen exe.
    Preference order:
      1) Next to exe / app_root (so user can override)
      2) Bundled into _MEIPASS (PyInstaller one-folder/one-file)
      3) Repo packaging/ directory (dev mode)
    """
    # 1) beside exe/app root
    p1 = (app_root / filename).resolve()
    if p1.is_file():
        return p1

    # 2) pyinstaller bundle
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p2 = (Path(meipass) / filename).resolve()
        if p2.is_file():
            return p2

    # 3) dev fallback
    p3 = (Path(__file__).resolve().parent / filename).resolve()
    return p3


def check_wsl_available() -> tuple[bool, str]:
    """检查 wsl 命令是否可用。"""
    try:
        r = subprocess.run(
            ["wsl", "--list", "--quiet"],
            capture_output=True,
            timeout=15,
            creationflags=_subprocess_creationflags(),
        )
        if r.returncode != 0:
            return False, "WSL 未正确安装或未启用，请先启用「适用于 Linux 的 Windows 子系统」。"
        return True, "WSL 可用"
    except FileNotFoundError:
        return False, "未找到 wsl 命令，请安装 WSL（Windows 功能 + Ubuntu 等发行版）。"
    except Exception as e:
        return False, str(e)


def enable_wsl_features_elevated() -> tuple[bool, str]:
    """
    以管理员权限启用 WSL 所需 Windows 功能。
    做法：写入临时 .bat，用「以管理员身份运行」执行，用户可在 CMD 窗口看到 dism 的完整输出；
    执行完毕后窗口会 pause，便于查看是否成功或报错。
    """
    import os
    import tempfile

    # 临时 .bat：DISM 成功时常返回 0 或 3010（需重启），只有这两种视为成功
    bat_content = r"""@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
echo ========================================
echo   InSAR WSL - Enabling Windows features
echo ========================================
echo.
echo [1/2] Microsoft-Windows-Subsystem-Linux ...
dism /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
if !errorlevel! equ 0 goto step2
if !errorlevel! equ 3010 goto step2
echo [FAIL] First DISM failed. Exit code: !errorlevel!
echo.
pause
exit /b 1
:step2
echo [OK] Done.
echo.
echo [2/2] VirtualMachinePlatform ...
dism /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
if !errorlevel! equ 0 goto done
if !errorlevel! equ 3010 goto done
echo [FAIL] Second DISM failed. Exit code: !errorlevel!
echo.
pause
exit /b 1
:done
echo [OK] Done.
echo.
echo ========================================
echo   Both features enabled. RESTART required.
echo ========================================
echo.
pause
exit /b 0
"""
    try:
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="insar_enable_wsl_", text=True)
        try:
            os.write(fd, bat_content.encode("utf-8"))
        finally:
            os.close(fd)
        bat_path = os.path.abspath(bat_path)

        # 用 PowerShell 以管理员身份启动该 .bat，-Wait 等待窗口关闭，-PassThru 以便取退出码
        ps_cmd = (
            f'$p = Start-Process -FilePath "cmd.exe" '
            f'-ArgumentList "/c", "{bat_path}" '
            f'-Verb RunAs -Wait -PassThru; exit $p.ExitCode'
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
            timeout=600,
            cwd=os.path.expanduser("~"),
        )
        try:
            os.unlink(bat_path)
        except OSError:
            pass
        if r.returncode != 0:
            return False, "启用过程中返回了错误，请查看刚才 CMD 窗口中的 dism 输出。"
        return True, "已启用 WSL 相关 Windows 功能。请务必重启电脑后再次打开本向导。若重启后仍不可用，请以管理员打开 PowerShell 运行：wsl --update"
    except subprocess.TimeoutExpired:
        return False, "启用超时，请查看弹出的 CMD 窗口是否仍在执行。"
    except Exception as e:
        return False, str(e)


def wsl_distro_exists() -> bool:
    """检查固定发行版名是否已存在（可能曾导入过）。"""
    try:
        r = subprocess.run(
            ["wsl", "--list", "--verbose"],
            capture_output=True,
            timeout=15,
            creationflags=_subprocess_creationflags(),
        )
        if r.returncode != 0:
            return False
        out = _decode_subprocess_output(r.stdout) + " " + _decode_subprocess_output(r.stderr)
        return WSL_DISTRO_NAME in out
    except Exception:
        return False


def wsl_unregister_distro() -> tuple[bool, str]:
    """卸载已存在的发行版，便于重新导入。"""
    try:
        r = subprocess.run(
            ["wsl", "--unregister", WSL_DISTRO_NAME],
            capture_output=True,
            timeout=60,
            creationflags=_subprocess_creationflags(),
        )
        out = _decode_subprocess_output(r.stdout) + " " + _decode_subprocess_output(r.stderr)
        if r.returncode != 0:
            return False, out or "卸载失败"
        return True, "已卸载"
    except Exception as e:
        return False, str(e)


def run_import(tar_path: str, target_dir: str) -> tuple[bool, str]:
    """执行 wsl --import（不弹控制台窗口）；错误信息用本机编码解码避免乱码。"""
    tar = Path(tar_path).resolve()
    target = Path(target_dir).resolve()
    if not tar.is_file():
        return False, f"镜像文件不存在：{tar}"
    target.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            ["wsl", "--import", WSL_DISTRO_NAME, str(target), str(tar)],
            capture_output=True,
            timeout=600,
            creationflags=_subprocess_creationflags(),
        )
        if r.returncode != 0:
            err = _decode_subprocess_output(r.stderr) or _decode_subprocess_output(r.stdout)
            if not err:
                err = "导入失败"
            if "already exists" in err.lower() or "已存在" in err or "exists" in err.lower():
                err = (
                    f"发行版「{WSL_DISTRO_NAME}」已存在（可能之前导入过）。"
                    "请先点击「执行导入并写入配置」时选择「是」先卸载再导入，或在本机以管理员运行：wsl --unregister " + WSL_DISTRO_NAME
                )
            return False, err
        return True, "导入成功"
    except subprocess.TimeoutExpired:
        return False, "导入超时"
    except Exception as e:
        return False, str(e)


def get_wsl_home() -> tuple[bool, str]:
    """在导入的发行版中获取 $HOME（用于拼接 INSAR_WSL_ENV_SCRIPT）。"""
    try:
        r = subprocess.run(
            ["wsl", "-d", WSL_DISTRO_NAME, "-e", "bash", "-c", "echo $HOME"],
            capture_output=True,
            timeout=15,
            creationflags=_subprocess_creationflags(),
        )
        home = _decode_subprocess_output(r.stdout)
        if r.returncode != 0 or not home:
            return False, ""
        return True, home
    except Exception:
        return False, ""


def get_wsl_path_from_windows(windows_path: str) -> tuple[bool, str]:
    """将 Windows 路径转为 WSL 路径（wslpath -a）。"""
    try:
        r = subprocess.run(
            ["wsl", "-e", "wslpath", "-a", windows_path],
            capture_output=True,
            timeout=10,
            creationflags=_subprocess_creationflags(),
        )
        wsl_path = _decode_subprocess_output(r.stdout)
        if r.returncode != 0 or not wsl_path:
            return False, ""
        return True, wsl_path
    except Exception:
        return False, ""


def write_wsl_config(
    app_root: Path,
    distro: str,
    env_script: str,
    project_root_wsl: str,
    weather_dir_wsl: str = "",
) -> None:
    """写入 wsl_config.env：同时写入固定用户路径（与 exe 位置无关）和应用根目录（兼容旧版）。"""
    lines = [
        f"INSAR_WSL_DISTRO={distro}",
        f"INSAR_WSL_ENV_SCRIPT={env_script}",
        f"INSAR_WSL_PROJECT_ROOT={project_root_wsl}",
    ]
    if (weather_dir_wsl or "").strip():
        lines.append(f"WEATHER_DIR={weather_dir_wsl.strip()}")
    content = "\n".join(lines) + "\n"
    # 1) 固定用户路径：Desktop 任意移动后仍能从此处读取
    try:
        from wsl_config_path import get_wsl_config_path, ensure_config_dir
        path = get_wsl_config_path()
        if path is not None and ensure_config_dir():
            path.write_text(content, encoding="utf-8")
    except Exception:
        pass
    # 2) 应用根目录（兼容旧部署与同目录使用）
    (app_root / "wsl_config.env").write_text(content, encoding="utf-8")


def _resolve_weather_dir_wsl(distro: str, weather_win: str) -> str:
    """将 Windows 气象目录转为 WSL 路径。"""
    if not weather_win.strip():
        return ""
    ok, wsl_path = get_wsl_path_from_windows(weather_win)
    if ok and wsl_path:
        return wsl_path
    try:
        r = subprocess.run(
            ["wsl", "-d", distro, "-e", "wslpath", "-a", weather_win.replace("\\", "/")],
            capture_output=True,
            timeout=20,
            creationflags=_subprocess_creationflags(),
        )
        if r.returncode == 0 and (r.stdout or b"").strip():
            return _decode_subprocess_output(r.stdout)
    except Exception:
        pass
    return ""


def finish_deploy_configuration(
    app_root: Path,
    env_script: str,
    project_root_wsl: str,
    *,
    cds_api_key: str = "",
    skip_cds: bool = False,
) -> tuple[bool, str]:
    """
    导入后写入 wsl_config、CDS（Windows + WSL）、气象缓存目录。
    返回 (成功, 给用户看的摘要信息)。
    """
    from packaging.wsl_sanitize import ensure_weather_dir_windows, push_cdsapirc_to_wsl
    from wsl_config_path import write_cdsapirc_windows

    notes: list[str] = []
    weather_win = ensure_weather_dir_windows() or ""
    weather_wsl = _resolve_weather_dir_wsl(WSL_DISTRO_NAME, weather_win) if weather_win else ""

    write_wsl_config(
        app_root,
        WSL_DISTRO_NAME,
        env_script,
        project_root_wsl,
        weather_dir_wsl=weather_wsl,
    )
    notes.append("已写入 wsl_config.env")

    if skip_cds:
        notes.append(
            "未配置 CDS API（MintPy 对流层 ERA5 需客户账号，可稍后「仅更新配置」补填）"
        )
    elif (cds_api_key or "").strip():
        try:
            write_cdsapirc_windows(cds_api_key.strip())
            notes.append("已保存 CDS 配置到本机用户目录")
        except OSError as e:
            return False, f"保存 CDS 配置失败：{e}"
        ok_cds, msg_cds = push_cdsapirc_to_wsl(
            WSL_DISTRO_NAME,
            cds_api_key.strip(),
            decode=_decode_subprocess_output,
            creationflags=_subprocess_creationflags(),
        )
        if not ok_cds:
            return False, f"写入 WSL CDS 配置失败：{msg_cds}"
        notes.append(msg_cds)
    else:
        from packaging.wsl_sanitize import sync_cdsapirc_from_windows_to_wsl

        ok_cds, msg_cds = sync_cdsapirc_from_windows_to_wsl(
            WSL_DISTRO_NAME,
            decode=_decode_subprocess_output,
            creationflags=_subprocess_creationflags(),
        )
        if not ok_cds:
            return False, msg_cds
        notes.append(msg_cds)

    if weather_wsl:
        notes.append(f"气象缓存目录（WEATHER_DIR）：{weather_wsl}")
    elif weather_win:
        notes.append("气象缓存目录已创建，但未能解析 WSL 路径（可在 wsl_config.env 中手动设置 WEATHER_DIR）")

    ok_env, msg_env = verify_wsl_env()
    if ok_env:
        notes.append(msg_env)
    else:
        notes.append(f"环境验证：{msg_env}")

    return True, "\n".join(notes)


def verify_wsl_env() -> tuple[bool, str]:
    """在导入的发行版中验证 isce/mintpy 可导入。"""
    try:
        r = subprocess.run(
            [
                "wsl", "-d", WSL_DISTRO_NAME, "-e", "bash", "-c",
                "source $HOME/insar-wsl/env_isce2.sh 2>/dev/null || true; "
                "python3 -c 'import isce; import mintpy' 2>&1",
            ],
            capture_output=True,
            timeout=30,
            creationflags=_subprocess_creationflags(),
        )
        if r.returncode != 0:
            msg = _decode_subprocess_output(r.stderr) or _decode_subprocess_output(r.stdout) or "验证失败"
            return False, msg
        return True, "ISCE2 与 MintPy 可用"
    except Exception as e:
        return False, str(e)


def main_ui(app_root: Path) -> None:
    from PySide6.QtWidgets import (
        QApplication,
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QPushButton,
        QFileDialog,
        QMessageBox,
        QProgressBar,
        QGroupBox,
        QFormLayout,
        QCheckBox,
    )
    from wsl_config_path import CDS_REGISTER_URL, cdsapirc_is_configured
    from PySide6.QtCore import Qt, QThread, Signal
    from PySide6.QtGui import QFont, QIcon

    class ImportWorker(QThread):
        """后台执行 wsl --import，避免主界面卡死。"""
        finished_signal = Signal(bool, str)

        def __init__(self, tar_path: str, target_path: str):
            super().__init__()
            self.tar_path = tar_path
            self.target_path = target_path

        def run(self) -> None:
            ok, msg = run_import(self.tar_path, self.target_path)
            self.finished_signal.emit(ok, msg)

    app = QApplication(sys.argv)
    app.setApplicationName("InSAR WSL 部署向导")

    win = QWidget()
    win.setWindowTitle("InSAR WSL 部署向导")
    icon_path = _resource_path(app_root, "wizard_icon.ico")
    if icon_path.is_file():
        icon = QIcon(str(icon_path))
        app.setWindowIcon(icon)
        win.setWindowIcon(icon)
    win.setMinimumWidth(520)
    layout = QVBoxLayout(win)

    # 应用根目录（只读显示）
    grp_root = QGroupBox("应用根目录（配置将写入此处）")
    form_root = QFormLayout(grp_root)
    root_edit = QLineEdit()
    root_edit.setReadOnly(True)
    root_edit.setText(str(app_root))
    form_root.addRow("路径：", root_edit)
    layout.addWidget(grp_root)

    # 已部署环境：仅更新配置（放在前面，方便老用户直接点）
    grp_update = QGroupBox("已部署过？仅更新配置（将代码路径设为安装根）")
    ly_update = QHBoxLayout(grp_update)
    btn_update_config = QPushButton("仅更新配置")
    hint_update = QLabel("若之前已导入过 WSL 镜像，后续更新时点此：选择更新包（文件夹或 ZIP）后，将自动覆盖安装根下的 backend、lib、scripts 并写入配置，无需再选 .tar 或手动复制。")
    hint_update.setWordWrap(True)
    ly_update.addWidget(btn_update_config)
    ly_update.addWidget(hint_update, 1)
    layout.addWidget(grp_update)

    # 步骤 1：WSL 镜像
    grp1 = QGroupBox("1. 选择 WSL 镜像文件（insar-wsl.tar）")
    ly1 = QHBoxLayout(grp1)
    tar_edit = QLineEdit()
    tar_edit.setPlaceholderText("选择 .tar 文件…")
    browse_tar = QPushButton("浏览…")
    def pick_tar():
        path, _ = QFileDialog.getOpenFileName(win, "选择 WSL 镜像", str(app_root), "TAR 文件 (*.tar);;全部 (*)")
        if path:
            tar_edit.setText(path)
    browse_tar.clicked.connect(pick_tar)
    ly1.addWidget(tar_edit)
    ly1.addWidget(browse_tar)
    layout.addWidget(grp1)

    # 步骤 2：导入目标目录
    grp2 = QGroupBox("2. 选择导入目标目录（发行版文件将存放于此）")
    ly2 = QHBoxLayout(grp2)
    target_edit = QLineEdit()
    target_edit.setPlaceholderText("例如 D:\\WSL\\InsarUbuntu24")
    browse_target = QPushButton("浏览…")
    def pick_target():
        path = QFileDialog.getExistingDirectory(win, "选择导入目标目录")
        if path:
            target_edit.setText(path)
    browse_target.clicked.connect(pick_target)
    ly2.addWidget(target_edit)
    ly2.addWidget(browse_target)
    layout.addWidget(grp2)

    grp_cds = QGroupBox("3. Copernicus CDS（MintPy 对流层 ERA5）")
    form_cds = QFormLayout(grp_cds)
    cds_key_edit = QLineEdit()
    cds_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
    cds_key_edit.setPlaceholderText("uid:api-key（在 CDS 网站注册后获取）")
    form_cds.addRow("API Key：", cds_key_edit)
    cds_skip_cb = QCheckBox("暂不配置（跳过在线下载 ERA5，可稍后在「仅更新配置」中补填）")
    cds_skip_cb.setChecked(False)
    form_cds.addRow("", cds_skip_cb)
    cds_hint = QLabel(
        f"对流层校正（MintPy 第 8 步）使用 ERA5 时需 Copernicus CDS 账号。"
        f' <a href="{CDS_REGISTER_URL}">免费注册 CDS</a>。'
        " 凭据仅保存在本机 %LOCALAPPDATA%\\InSAR\\，不会写入 WSL 镜像。"
    )
    cds_hint.setWordWrap(True)
    cds_hint.setOpenExternalLinks(True)
    cds_hint.setTextFormat(Qt.TextFormat.RichText)
    layout.addWidget(grp_cds)
    layout.addWidget(cds_hint)
    if cdsapirc_is_configured():
        cds_key_edit.setPlaceholderText("已配置（留空则保持原 Key，仅同步到 WSL）")

    btn_save_cds = QPushButton("保存 CDS 并同步到 WSL（不重新导入镜像）")

    def do_save_cds_only() -> None:
        ok, _ = check_wsl_available()
        if not ok:
            status.setText("WSL 不可用。")
            return
        if not wsl_distro_exists():
            QMessageBox.information(
                win,
                "未部署",
                "请先完成 WSL 镜像导入，或确认发行版 InsarUbuntu24 已存在。",
            )
            return
        if not _validate_cds_before_deploy():
            return
        install_root = _code_install_root(app_root)
        ok_path, project_root_wsl = get_wsl_path_from_windows(str(install_root))
        if not ok_path or not project_root_wsl:
            ok_path, project_root_wsl = get_wsl_path_from_windows(str(app_root))
        if not project_root_wsl:
            QMessageBox.warning(win, "路径错误", "无法解析安装根目录 WSL 路径。")
            return
        ok_home, home = get_wsl_home()
        env_script = f"{home}/insar-wsl/env_isce2.sh" if ok_home and home else "/home/insar/insar-wsl/env_isce2.sh"
        cds_key, skip_cds = _cds_params_for_deploy()
        progress.setVisible(True)
        progress.setRange(0, 0)
        ok_cfg, cfg_msg = finish_deploy_configuration(
            app_root,
            env_script,
            project_root_wsl,
            cds_api_key=cds_key,
            skip_cds=skip_cds,
        )
        progress.setVisible(False)
        if ok_cfg:
            status.setText("CDS/配置已保存。")
            QMessageBox.information(win, "完成", cfg_msg)
        else:
            status.setText(cfg_msg)
            QMessageBox.warning(win, "失败", cfg_msg)

    btn_save_cds.clicked.connect(do_save_cds_only)
    layout.addWidget(btn_save_cds)

    # WSL 一键启用
    grp0 = QGroupBox("0. 启用 WSL（若未启用）")
    ly0 = QHBoxLayout(grp0)
    btn_enable = QPushButton("一键启用 WSL（管理员）")
    btn_check = QPushButton("重新检测 WSL")
    ly0.addWidget(btn_enable)
    ly0.addWidget(btn_check)
    layout.addWidget(grp0)

    progress = QProgressBar()
    progress.setVisible(False)
    layout.addWidget(progress)

    status = QLabel("")
    status.setWordWrap(True)
    layout.addWidget(status)

    def _cds_params_for_deploy() -> tuple[str, bool]:
        if cds_skip_cb.isChecked():
            return "", True
        key = cds_key_edit.text().strip()
        if key:
            return key, False
        if cdsapirc_is_configured():
            return "", False
        return "", True

    def _validate_cds_before_deploy() -> bool:
        if cds_skip_cb.isChecked():
            return True
        if cds_key_edit.text().strip() or cdsapirc_is_configured():
            return True
        QMessageBox.warning(
            win,
            "CDS 未配置",
            "请填写 CDS API Key（格式 uid:api-key），或勾选「暂不配置」。\n\n"
            "MintPy 对流层 ERA5 需要客户自己的 CDS 账号，不会使用开发商个人账号。",
        )
        return False

    def do_check() -> None:
        ok, msg = check_wsl_available()
        if not ok:
            status.setText("⚠ " + msg + "。可点击「一键启用 WSL（管理员）」后重启，再回到此向导继续导入。")
        else:
            if wsl_distro_exists():
                status.setText("✓ " + msg + "。检测到已部署的 WSL 环境；若只需更新代码路径，请点击「仅更新配置」。首次部署请选择镜像与导入目标后点击「执行导入并写入配置」。")
            else:
                status.setText("✓ " + msg + "。请选择镜像文件与导入目标目录后点击「执行导入并写入配置」。")

    def _choose_update_source() -> Optional[Path]:
        """让用户选择更新包（文件夹或 ZIP），返回包含 backend/lib/scripts 的目录路径；取消则返回 None。"""
        msg = QMessageBox(win)
        msg.setWindowTitle("选择更新包来源")
        msg.setText("请选择包含 backend、lib、scripts 的更新包：")
        msg.setIcon(QMessageBox.Icon.Question)
        btn_folder = msg.addButton("选择文件夹", QMessageBox.ButtonRole.ActionRole)
        btn_zip = msg.addButton("选择 ZIP 文件", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_folder:
            path = QFileDialog.getExistingDirectory(
                win,
                "选择更新包文件夹（需包含 backend、lib、scripts）",
                str(app_root.parent),
            )
            return Path(path) if path else None
        if clicked == btn_zip:
            path, _ = QFileDialog.getOpenFileName(
                win,
                "选择更新包 ZIP 文件",
                str(app_root.parent),
                "ZIP 文件 (*.zip);;所有文件 (*.*)",
            )
            if not path:
                return None
            tmp = Path(tempfile.mkdtemp(prefix="insar_update_"))
            try:
                with zipfile.ZipFile(path, "r") as zf:
                    zf.extractall(tmp)
                return tmp
            except Exception as e:
                QMessageBox.warning(win, "解压失败", f"无法解压 ZIP：{e}")
                if tmp.exists():
                    try:
                        shutil.rmtree(tmp, ignore_errors=True)
                    except Exception:
                        pass
                return None
        return None

    def _copy_update_folders(source: Path, install_root: Path) -> tuple[bool, str]:
        """将 source 下的 backend、lib、scripts 覆盖复制到 install_root。返回 (成功, 错误信息)。"""
        names = ("backend", "lib", "scripts")
        root = source
        found = [n for n in names if (root / n).is_dir()]
        if not found and root.is_dir():
            subdirs = [p for p in root.iterdir() if p.is_dir()]
            if len(subdirs) == 1 and any((subdirs[0] / n).is_dir() for n in names):
                root = subdirs[0]
                found = [n for n in names if (root / n).is_dir()]
        if not found:
            return False, "更新包中未找到 backend、lib 或 scripts 文件夹。"
        try:
            for n in found:
                src = root / n
                dst = install_root / n
                # backend/scripts：整体覆盖；lib：尽量合并（避免更新包只带部分 lib 时误删用户现有内容）
                if n in ("backend", "scripts"):
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copytree(src, dst, dirs_exist_ok=True)
            return True, ""
        except Exception as e:
            return False, str(e)

    def do_update_config_only() -> None:
        """已部署过：选择更新包 → 覆盖 backend/lib/scripts → 写入配置，用户无需再手动操作。"""
        ok, _ = check_wsl_available()
        if not ok:
            status.setText("WSL 不可用，无法更新配置。请先启用 WSL 后再试。")
            return
        if not wsl_distro_exists():
            QMessageBox.information(
                win,
                "未检测到已部署环境",
                "未检测到已导入的 WSL 发行版（InsarUbuntu24）。\n请先执行「执行导入并写入配置」完成首次部署。",
            )
            status.setText("未检测到已导入的 WSL 发行版，请先执行「执行导入并写入配置」。")
            return
        install_root = app_root.parent
        source = _choose_update_source()
        if not source or not source.is_dir():
            status.setText("未选择更新包，已取消。")
            return
        progress.setVisible(True)
        progress.setRange(0, 0)
        status.setText("正在覆盖 backend、lib、scripts…")
        QApplication.processEvents()
        copy_ok, copy_err = _copy_update_folders(source, install_root)
        # 若更新包来自 ZIP 解压的临时目录，复制完成后删除
        try:
            tmp_dir = Path(tempfile.gettempdir()).resolve()
            if tmp_dir in source.resolve().parents and "insar_update_" in source.name:
                shutil.rmtree(source, ignore_errors=True)
        except Exception:
            pass
        if not copy_ok:
            progress.setVisible(False)
            status.setText(f"覆盖失败：{copy_err}")
            QMessageBox.warning(win, "更新失败", f"覆盖 backend/lib/scripts 失败：{copy_err}")
            return
        status.setText("正在写入配置…")
        QApplication.processEvents()
        ok_path, project_root_wsl = get_wsl_path_from_windows(str(install_root))
        if not ok_path or not project_root_wsl:
            ok_path, project_root_wsl = get_wsl_path_from_windows(str(app_root))
        if not ok_path or not project_root_wsl:
            progress.setVisible(False)
            status.setText("无法解析安装根目录的 WSL 路径，请检查路径或手动编辑 wsl_config.env。")
            QMessageBox.warning(
                win,
                "配置写入失败",
                "无法将安装根目录转为 WSL 路径。请手动编辑 %LOCALAPPDATA%\\InSAR\\wsl_config.env 中的 INSAR_WSL_PROJECT_ROOT。",
            )
            return
        ok_home, home = get_wsl_home()
        env_script = f"{home}/insar-wsl/env_isce2.sh" if ok_home and home else "/home/insar/insar-wsl/env_isce2.sh"
        cds_key, skip_cds = _cds_params_for_deploy()
        ok_cfg, cfg_msg = finish_deploy_configuration(
            app_root,
            env_script,
            project_root_wsl,
            cds_api_key=cds_key,
            skip_cds=skip_cds,
        )
        progress.setVisible(False)
        if not ok_cfg:
            status.setText(f"配置写入失败：{cfg_msg}")
            QMessageBox.warning(win, "配置失败", cfg_msg)
            return
        status.setText("更新完成：已覆盖 backend/lib/scripts 并写入配置，可直接启动 InSAR Desktop。")
        # 更新后检查关键脚本是否存在（避免 DEM 等功能因缺失 isce2 脚本报错）
        dem_py = install_root / "lib" / "isce2-main" / "applications" / "dem.py"
        if not dem_py.is_file():
            QMessageBox.warning(
                win,
                "更新完成（但检测到缺失文件）",
                "已完成覆盖与配置写入，但检测到缺失：\n"
                f"  {dem_py}\n\n"
                "这可能导致「DEM 制作」等功能报错。\n"
                "请在更新包中包含 lib/isce2-main/applications（至少 dem.py），或将完整的 lib/isce2-main 目录补齐后再点一次「仅更新配置」。",
            )
            return
        QMessageBox.information(
            win,
            "更新完成",
            "已从更新包覆盖 backend、lib、scripts 到安装根目录，并已写入 WSL 配置。\n\n"
            + cfg_msg
            + "\n\n请启动 InSAR Desktop 使用。",
        )

    def do_enable_wsl() -> None:
        progress.setVisible(True)
        progress.setRange(0, 0)
        status.setText("正在启用 WSL 相关 Windows 功能（将弹出管理员确认）…")
        QApplication.processEvents()
        ok, msg = enable_wsl_features_elevated()
        progress.setVisible(False)
        if not ok:
            status.setText("启用失败：" + msg)
            QMessageBox.warning(win, "启用失败", msg)
            return
        status.setText(msg + " 请重启电脑后点击「重新检测 WSL」。")
        QMessageBox.information(win, "已完成", msg + "\n\n通常需要重启后生效。请重启电脑后重新打开本向导继续部署。")

    def on_import_finished(ok: bool, msg: str) -> None:
        progress.setVisible(False)
        btn_import.setEnabled(True)
        win._import_worker = None  # 允许回收
        if not ok:
            status.setText(f"导入失败：{msg}")
            QMessageBox.warning(win, "导入失败", msg)
            return
        status.setText("导入成功，正在写入配置…")
        QApplication.processEvents()
        ok_home, home = get_wsl_home()
        env_script = f"{home}/insar-wsl/env_isce2.sh" if ok_home and home else "/home/insar/insar-wsl/env_isce2.sh"
        # 安装根目录（向导 exe 的上一级）：代码放此处，WSL 只读此路径下 backend/、lib/、scripts/，
        # 后续仅需更新该目录下的代码即可完成软件更新，无需重新导出/导入 WSL 镜像。
        install_root = _code_install_root(app_root)
        ok_path, project_root_wsl = get_wsl_path_from_windows(str(install_root))
        if not ok_path or not project_root_wsl:
            ok_path, project_root_wsl = get_wsl_path_from_windows(str(app_root))
        if not ok_path or not project_root_wsl:
            status.setText("无法解析安装根目录的 WSL 路径，请手动编辑 wsl_config.env 中的 INSAR_WSL_PROJECT_ROOT。")
            project_root_wsl = ""
        cds_key, skip_cds = _cds_params_for_deploy()
        ok_cfg, cfg_msg = finish_deploy_configuration(
            app_root,
            env_script,
            project_root_wsl,
            cds_api_key=cds_key,
            skip_cds=skip_cds,
        )
        if not ok_cfg:
            status.setText("导入成功，但配置写入失败：" + cfg_msg)
            QMessageBox.warning(
                win,
                "配置未完成",
                "WSL 已导入，但 CDS/配置写入失败：\n" + cfg_msg,
            )
            return
        status.setText("配置已写入。可关闭向导并启动 InSAR Desktop。")
        QMessageBox.information(
            win,
            "完成",
            "WSL 环境已导入。\n\n" + cfg_msg + "\n\n请启动 InSAR Desktop 使用。",
        )

    def do_import() -> None:
        tar_path = tar_edit.text().strip()
        target_path = target_edit.text().strip()
        ok, _ = check_wsl_available()
        if not ok:
            status.setText("WSL 不可用。请先启用 WSL（点击上方「一键启用 WSL（管理员）」并重启），再导入镜像。")
            return
        if not tar_path:
            status.setText("请选择 WSL 镜像文件。")
            return
        if not target_path:
            status.setText("请选择导入目标目录。")
            return
        if not _validate_cds_before_deploy():
            return
        if getattr(win, "_import_worker", None) and win._import_worker.isRunning():
            return
        if wsl_distro_exists():
            ret = QMessageBox.question(
                win,
                "发行版已存在",
                f"发行版「{WSL_DISTRO_NAME}」已存在（可能曾导入过但已删除文件）。是否先卸载再重新导入？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ret == QMessageBox.StandardButton.Yes:
                status.setText("正在卸载已有发行版…")
                QApplication.processEvents()
                unreg_ok, unreg_msg = wsl_unregister_distro()
                if not unreg_ok:
                    status.setText(f"卸载失败：{unreg_msg}")
                    QMessageBox.warning(win, "卸载失败", unreg_msg)
                    return
                status.setText("已卸载，开始导入…")
            else:
                return
        btn_import.setEnabled(False)
        progress.setVisible(True)
        progress.setRange(0, 0)
        status.setText("正在导入 WSL 镜像（约需数分钟，请勿关闭窗口）…")
        worker = ImportWorker(tar_path, target_path)
        worker.finished_signal.connect(on_import_finished)
        win._import_worker = worker
        worker.start()

    btn_import = QPushButton("执行导入并写入配置")
    btn_import.clicked.connect(do_import)
    layout.addWidget(btn_import)

    btn_update_config.clicked.connect(do_update_config_only)
    btn_enable.clicked.connect(do_enable_wsl)
    btn_check.clicked.connect(do_check)

    # 初始检查
    do_check()

    win.show()
    sys.exit(app.exec())


def main() -> None:
    parser = argparse.ArgumentParser(description="InSAR WSL 部署向导")
    parser.add_argument("--app-root", type=str, help="应用根目录（配置写入该目录下的 wsl_config.env）")
    args = parser.parse_args()
    app_root = _get_app_root(args.app_root)
    main_ui(app_root)


if __name__ == "__main__":
    main()
