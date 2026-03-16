# InSAR 桌面端 (PySide6)

基于 PySide6 的本地桌面 UI，**直接调用 ISCE2 处理函数**，无需启动 FastAPI/Celery/Redis。支持原生文件夹选择（完整 Windows 路径）、工程管理、Sentinel-1 导入（run_1）及大栅格显示。

## 目录结构

- `main.py` — 应用入口
- `app/` — 应用逻辑与界面
  - `main_window.py` — 主窗口
  - `project_store.py` — 工程列表与当前项目本地持久化
  - `widgets/` — 自定义控件（地图、表单、S1 导入对话框等）
  - `api/` — 可选 HTTP 客户端（主流程已改为本地直连）
  - `ui/` — Qt Designer 的 .ui 文件（可选）
  - `resources/` — 图标等资源（可选）
- `requirements.txt` — 仅用 UI 时的最小依赖
- `requirements-isce.txt` — **桌面直连 ISCE 时**在 isce2-build 中安装的依赖

## 运行（桌面直连 ISCE，推荐）

需使用能加载 ISCE2 的 Python（conda **isce2-build** 环境），并安装桌面+处理依赖：

```powershell
# 在 isce2-build 中安装依赖（项目根目录执行）
pip install -r desktop/requirements-isce.txt

# 双击或在终端运行启动脚本（自动检测 .venv / isce2-build，设置环境变量）
scripts\start_desktop.bat
```

脚本会自动设置 `PYTHONPATH`、`PYTHONIOENCODING` 等；若用 isce2-build 回退，还会设置 UCRT64 与 ISCE packages PATH。详见 `docs/windows-phase4.md`。

## WSL 模式（推荐：处理在 WSL 内执行）

处理在 WSL2（如 Ubuntu 24.04）内运行，Desktop 仅需 .venv，无需在 Windows 下安装 ISCE2：

```batch
scripts\start_desktop_wsl.bat
```

脚本会设置 `INSAR_USE_WSL=1`、`INSAR_WSL_PROJECT_ROOT` 等，并检查 WSL 可用后启动 Desktop。使用前需在 WSL 内按 `docs/wsl_ubuntu24_isce2_setup.md` 配置 ISCE2 + MintPy，并在 WSL 内保留一份本仓库（如 `~/insar-system`）。可选：在脚本内或启动前设置 `INSAR_WSL_DISTRO`、`INSAR_WSL_ENV_SCRIPT` 等覆盖默认值。

## 仅 UI 不跑 ISCE 时

若只打开界面、不执行 S1 导入，可在项目 `.venv` 下：

```bash
pip install -r desktop/requirements.txt
python -m desktop.main
```

此时无需后端 API；工程数据仍从本地 `project_store` 读写。
