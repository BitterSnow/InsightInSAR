# InSAR Desktop 安装与交付

本文简述桌面端打包、安装及 WSL 处理环境的两种部署方式（在线 / 离线）。

## 交付物

- **InSAR Desktop**：Windows 桌面程序（PyInstaller one-folder 或安装包），双击运行，无需用户安装 Python/PySide6。
- **WSL 处理环境**：ISCE2 + MintPy 运行在 WSL2（Ubuntu）内，由 Desktop 通过 WSL 桥接调用。
- **可选**：**InSAR WSL 部署向导**：离线导入预导出的 WSL 镜像并写入 `wsl_config.env`。

## 部署方式

### 在线部署（开发 / 有网络）

1. 用户安装 WSL2 与 Ubuntu，在 WSL 内按 [docs/wsl_ubuntu24_isce2_setup.md](wsl_ubuntu24_isce2_setup.md) 配置 Miniconda、ISCE2、MintPy。
2. 在 Windows 上设置环境变量（或使用 `scripts/start_desktop_wsl.bat`）：`INSAR_USE_WSL=1`、`INSAR_WSL_PROJECT_ROOT`、`INSAR_WSL_ENV_SCRIPT` 等。
3. 启动 Desktop（或通过 `scripts/start_desktop_wsl.bat`）。

详见 [wsl_ubuntu24_isce2_setup.md](wsl_ubuntu24_isce2_setup.md)。

### 离线部署（无网络 / 客户现场）

1. **构建阶段**（有网络）：在构建机上运行 **`packaging/export_wsl_image.bat`**（或 `powershell -File packaging/export_wsl_image.ps1`），在 `dist/insar-wsl.tar` 生成 WSL 镜像；或将 WSL 环境按文档配置后手动 `wsl --export` 得到 `insar-wsl.tar`，随安装包或与部署向导一起交付。
2. **用户机**：安装 InSAR Desktop（及可选「InSAR WSL 部署向导」）；确保 Windows 已启用 WSL。
3. 用户运行 **InSAR WSL 部署向导**，选择 `insar-wsl.tar` 与导入目标目录，执行导入；向导将 `INSAR_WSL_DISTRO`、`INSAR_WSL_ENV_SCRIPT`、`INSAR_WSL_PROJECT_ROOT` 写入安装目录下的 `wsl_config.env`。
4. 启动 InSAR Desktop；主程序启动时自动加载 `wsl_config.env`，无需用户手动设置环境变量。

详见 [wsl_ubuntu24_isce2_setup.md](wsl_ubuntu24_isce2_setup.md) 第 10 节与 [packaging/README.md](../packaging/README.md)。

### 环境与代码分离（便于后续仅更新代码）

- **WSL 镜像（insar-wsl.tar）**：仅含 Ubuntu + ISCE2 + MintPy 环境，更新频率低。
- **代码位置**：部署向导将 `INSAR_WSL_PROJECT_ROOT` 设为**安装根目录**（向导 exe 的上一级）的 WSL 路径；该目录下放置 `backend/`、`lib/MintPy-main/`、`scripts/` 等，WSL 通过 `/mnt/...` 访问。
- **软件更新**：仅业务或脚本变更时，用新版本覆盖安装根目录下的 `backend/`、`lib/`、`scripts/` 即可，无需重新导入 tar；仅在环境升级时需重新导出并导入新镜像。详见 [packaging/README.md](../packaging/README.md)「环境与代码分离」一节。

## 打包与安装包构建

- **桌面端 + 向导**：见 [packaging/README.md](../packaging/README.md)（PyInstaller spec、构建步骤、部署向导用法）。
- **Windows 安装包**：见 [packaging/installer/README.md](../packaging/installer/README.md)（Inno Setup 脚本与构建说明）。
