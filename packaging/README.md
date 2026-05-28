# InSAR Desktop 打包说明

## 阶段 1：桌面端 one-folder 构建

### 环境

- Windows 10/11，Python 3.11+
- 安装桌面依赖与 PyInstaller：
  ```bash
  pip install -r desktop/requirements.txt
  pip install pyinstaller
  ```

### 构建（推荐一键）

双击 **`packaging/build_all.bat`**，将自动打包桌面端、WSL 部署向导与 WSL 导出向导，产出在 `dist/` 下（无需再手动运行脚本）。

如需给客户生成“少量更新包”（供向导「仅更新配置」一键覆盖 `backend/lib/scripts`），双击：

- `packaging/make_update_package.bat` → 生成 `dist/insar-update-*.zip`

或手动在**项目根目录**执行（需先从 `.venv` 目录运行以避免与本地 `packaging` 目录名冲突）：

```bash
cd .venv
.\Scripts\python.exe -m PyInstaller --noconfirm --distpath=..\dist --workpath=..\build ..\packaging\insar_desktop.spec
cd ..
```

产出目录：`dist/InSAR Desktop/`，内含：

- `InSAR Desktop.exe` — 主程序
- `backend/`、`desktop/`、`shared_models.py` — 随包数据（与 exe 同层）
- 其他 PyInstaller 运行时文件

### 部署（含 WSL 使用）

采用「环境与代码分离」时，**安装根目录**为 `dist/`（与 `InSAR Desktop/`、`InSAR WSL Deploy Wizard/` 同级）。请将以下目录复制到 **`dist/`** 下，供 WSL 通过 `INSAR_WSL_PROJECT_ROOT` 访问：

- `backend/`
- `lib/isce2-main/`（至少保留 `contrib/stack/topsStack` 等脚本）
- `lib/MintPy-main/`（至少 `src`）
- `scripts/`（可选，按需）

即 `dist/` 下除两个 exe 目录和 `insar-wsl.tar` 外，还包含 `backend/`、`lib/` 等；部署向导会将 `INSAR_WSL_PROJECT_ROOT` 设为 `dist/` 的 WSL 路径。

### 打包版行为

- **应用根目录**：exe 所在目录（冻结时）。
- **默认 WSL 模式**：`INSAR_USE_WSL=1`，不依赖本机 ISCE2。
- **WSL 配置**：若存在同目录下的 `wsl_config.env`（部署向导生成），启动时自动加载为环境变量（如 `INSAR_WSL_DISTRO`、`INSAR_WSL_ENV_SCRIPT`、`INSAR_WSL_PROJECT_ROOT`）。

---

## 阶段 2：WSL 部署向导

### 构建向导 exe（可选）

在项目根目录执行：

```bash
pyinstaller packaging/wsl_deploy_wizard.spec
```

产出：`dist/InSAR WSL Deploy Wizard/`，内含 `InSAR WSL Deploy Wizard.exe`。可将该 exe 与同目录下依赖文件一并复制到「InSAR Desktop」目录，或通过安装包安装后与主程序同目录，用户双击即可运行向导。

### 构建 WSL 导出向导 exe（可选）

在项目根目录执行：

```bash
pyinstaller packaging/wsl_export_wizard.spec
```

产出：`dist/InSAR WSL Export Wizard/`，内含 `InSAR WSL Export Wizard.exe`。该工具用于在构建机上选择本机 WSL 发行版并导出为 `.tar` 镜像（用于离线交付）。

### 不打包时直接运行

```bash
python -m packaging.wsl_deploy_wizard [--app-root "D:\InSAR"]
```
（需在项目根执行，且未重命名 `packaging` 目录）

需已安装 `desktop/requirements.txt`（PySide6 等）。`--app-root` 不填时，默认为当前项目根或（冻结时）exe 所在目录。

### 向导流程

1. 检查 WSL 是否可用。
2. 用户选择 `insar-wsl.tar` 路径及导入目标目录。
3. 执行 `wsl --import InsarUbuntu24 <目标> <tar>`。
4. 检测 WSL 内 `$HOME` 并拼出 `INSAR_WSL_ENV_SCRIPT`，将**安装根目录**（向导 exe 所在目录的上一级）转为 WSL 路径作为 `INSAR_WSL_PROJECT_ROOT`。
5. 在应用根目录及本机固定路径写入 `wsl_config.env`，供 Desktop 启动时加载。

**离线用 WSL 镜像**：需在**有网络的构建机**上导出一份 `insar-wsl.tar`，与 Desktop/向导 一起拷贝到离线环境。  
在项目根目录双击 **`packaging/export_wsl_image.bat`**（或运行 `powershell -File packaging/export_wsl_image.ps1`），会在 `dist/insar-wsl.tar` 生成镜像；构建机需已安装 WSL2 与 Ubuntu，脚本会在 WSL 内自动检查/安装 ISCE2+MintPy 后导出。详见 `docs/wsl_ubuntu24_isce2_setup.md` 第 10 节。

---

## 离线交付清单（拷贝到离线环境即可部署）

| 内容 | 来源 | 说明 |
|------|------|------|
| 主程序 | `dist/InSAR Desktop/` | 整目录拷贝，双击 `InSAR Desktop.exe` 运行 |
| WSL 部署向导 | `dist/InSAR WSL Deploy Wizard/` | 整目录拷贝，双击 `InSAR WSL Deploy Wizard.exe` 运行 |
| WSL 导出向导 | `dist/InSAR WSL Export Wizard/` | 构建机使用，双击 `InSAR WSL Export Wizard.exe` 选择发行版并导出 `insar-wsl.tar` |
| WSL 镜像 | `dist/insar-wsl.tar` | 需在**有网络**的构建机先运行 `packaging/export_wsl_image.bat` 生成，再与上两项一起拷贝 |

离线机上：先运行部署向导，选择 `insar-wsl.tar` 与导入目标目录完成导入；再运行 Desktop。若未拷贝 `insar-wsl.tar`，离线机无法使用 WSL 处理，仅可先配置工程与界面。

---

## 环境与代码分离（推荐部署方式）

为便于**只更新业务代码、无需重新导出/导入 WSL 镜像**，采用「WSL 镜像仅含环境、代码在 Windows 安装根」的分离方式。

### 约定

- **WSL 镜像（insar-wsl.tar）**：仅包含 Ubuntu + ISCE2 + MintPy 运行环境（Miniconda、env 脚本等），**不包含**项目代码。更新频率低，仅在环境升级时重新导出。
- **安装根目录**：向导 exe 所在目录的**上一级**。配置中的 `INSAR_WSL_PROJECT_ROOT` 指向该目录的 WSL 路径（如 `/mnt/d/InSAR`）。WSL 内执行的脚本、`backend/`、`lib/MintPy-main/` 等均从此路径读取。
- **推荐目录结构**（安装根目录下）：
  ```
  安装根目录/
  ├── InSAR Desktop/          # 主程序（整目录）
  ├── InSAR WSL Deploy Wizard/# 部署向导（整目录）
  ├── backend/                # 后端脚本（可单独更新）
  ├── lib/
  │   ├── isce2-main/        # 可选，按需
  │   └── MintPy-main/       # 至少保留 src
  └── scripts/               # 脚本（可单独更新）
  ```

### 软件更新（仅更新代码、不重导镜像）

1. **仅业务/脚本更新**：用新版本的 `backend/`、`lib/MintPy-main/`、`scripts/` 覆盖安装根目录下对应文件夹即可，无需重新运行部署向导或重新导入 `insar-wsl.tar`。
2. **主程序/向导更新**：用新版本的 `InSAR Desktop/`、`InSAR WSL Deploy Wizard/` 覆盖原目录；`wsl_config.env` 已写入本机固定路径（`%LOCALAPPDATA%\InSAR\wsl_config.env`），一般无需重配。
3. **环境升级**（如 ISCE2/MintPy 版本升级）：需在构建机重新导出 `insar-wsl.tar`，用户重新运行部署向导选择新 tar 导入（或先卸载旧发行版再导入）。

导出「仅含环境」的镜像时，构建机 WSL 内不要将项目代码放在 `~/insar-system`，仅保留 `~/insar-wsl/env_isce2.sh` 等环境配置；或使用当前 `export_wsl_image.ps1` 导出后，用户侧仍以安装根目录为代码来源（WSL 通过 `/mnt/...` 访问），代码更新方式同上。

## 阶段 3：安装程序与文档

- 安装脚本：见 `packaging/installer/`（如使用 Inno Setup）。
- 在线/离线部署说明：见 `docs/wsl_ubuntu24_isce2_setup.md`（在线配置与 §10 离线部署）。
