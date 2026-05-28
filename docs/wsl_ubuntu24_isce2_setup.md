# WSL2 Ubuntu 24.04 下 ISCE2 + MintPy 环境配置

本文档说明在 WSL2 中的 Ubuntu 24.04 上配置 ISCE2、MintPy 及 Snaphu，供 Desktop（Windows）通过 WSL 桥接调用。**桥接固定使用 Ubuntu 发行版**（代码中默认 `-d Ubuntu`），不使用系统默认发行版（如 docker-desktop）。代码建议在 WSL 内保留一份（如 `~/insar-system`），便于脚本路径使用 WSL 原生路径。

## 1. 前置条件

- Windows 10/11 已安装 WSL2，并已安装 **Ubuntu**（推荐 24.04 或 22.04）。桥接仅调用 Ubuntu，无需将 Ubuntu 设为系统默认 WSL。若出现 `execvpe (bash) failed`，请确认已从 Microsoft Store 安装 Ubuntu。
- 在 **WSL Ubuntu** 终端中执行以下步骤。

## 2. 系统依赖（可选，若从源码编译 ISCE2 则需要）

若使用 conda 安装预编译的 ISCE2，可跳过部分系统库；若从源码用 SCons 编译，需安装：

```bash
sudo apt update
sudo apt install -y build-essential cmake gfortran libfftw3-dev libgdal-dev \
  python3-dev libhdf5-dev libncurses5-dev curl
```

## 3. 安装 Miniconda 与 ISCE2 / MintPy（推荐）

在 WSL 用户目录下安装 Miniconda，再创建专用环境：

```bash
cd ~
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
bash Miniconda3-latest-Linux-x86_64.sh -b -p ~/miniconda3
~/miniconda3/bin/conda init bash
# 重新打开终端或 source ~/.bashrc
```

创建环境并安装 ISCE2、MintPy（仅用 conda-forge，避免 Anaconda 默认频道需接受条款）：

```bash
conda create -n isce2 --override-channels -c conda-forge python=3.11 isce2 mintpy -y
conda activate isce2
```

若曾因「Terms of Service have not been accepted」创建失败，可删除不完整环境后重跑：`conda env remove -n isce2 -y`，再执行 `scripts/wsl/setup_isce2_ubuntu24.sh` 或 `scripts\ensure_wsl_env.bat`。

验证：

```bash
python -c "import isce; print(isce.__file__)"
python -c "import mintpy; print(mintpy.__file__)"
```

## 4. Snaphu（解缠）

- **方式 A（apt）**：若 Ubuntu 提供 snaphu 包：

  ```bash
  sudo apt install -y snaphu
  which snaphu
  ```

- **方式 B（conda）**：在 isce2 环境中尝试：

  ```bash
  conda activate isce2
  conda install -c conda-forge snaphu  # 若有
  ```

- **方式 C（源码）**：从 [Snaphu 官方](https://web.stanford.edu/group/radar/softwareandtools/snaphu/) 下载并编译，将可执行文件所在目录加入 PATH，或通过环境变量 `SNAPHU_BIN` 指定。

## 5. 代码在 WSL 内的位置

建议将本仓库在 WSL 内保留一份，便于桥接时使用 WSL 原生路径调用脚本，避免通过 `/mnt/...` 访问 Windows 盘上的代码。例如：

```bash
cd ~
git clone <本项目仓库地址> insar-system
# 或从 Windows 复制到 WSL：在 Windows 上复制 d:\coding\insar-system 到 \\wsl$\Ubuntu\home\<用户>\insar-system
```

约定：

- 项目根：`~/insar-system`（或 `/home/<用户>/insar-system`）。
- Stack 脚本（conda isce2）：`$CONDA_PREFIX/share/isce2/topsStack/stackSentinel.py`（桥接自动探测，勿指向 `/mnt/...` 下 Windows 源码树）。
- DEM：`$CONDA_PREFIX/lib/python3.11/site-packages/isce/applications/dem.py`（由 `import isce` 解析）。

## 6. 环境激活脚本（供桥接调用前 source）

创建 `~/insar-wsl/env_isce2.sh`（或项目内 `scripts/wsl/env_isce2.sh`），供 Windows 侧通过 `wsl -e bash -c 'source ...; 命令'` 在一致环境中执行：

```bash
#!/usr/bin/env bash
# 供 WSL 桥接在执行 ISCE2/MintPy 前 source
set -e
if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  source "$HOME/miniconda3/etc/profile.d/conda.sh"
  conda activate isce2
fi
# 若 Snaphu 在自定义目录，可在此 export
# export SNAPHU_BIN=/path/to/snaphu/bin
# 项目代码路径（用于 Python 找 topsStack 等）
export INSAR_PROJECT_ROOT="${INSAR_PROJECT_ROOT:-$HOME/insar-system}"
# topsStack / ISCE 包路径由 conda 提供，见 scripts/wsl/env_isce2.sh
```

桥接时会传入 `INSAR_PROJECT_ROOT`（WSL 路径），无需在脚本内写死。

**Windows 侧必须设置的环境变量**（在运行 Desktop 或后端前设置，否则 WSL 内会报 `No module named 'numpy'` 等）：

| 变量 | 说明 | 示例（WSL 路径） |
|------|------|------------------|
| `INSAR_WSL_ENV_SCRIPT` | 上述环境脚本的 **WSL 绝对路径**，供桥接在执行前 `source` | `C:\...` 不可用，需 WSL 路径如 `/home/你的用户名/insar-wsl/env_isce2.sh` |
| `INSAR_WSL_PROJECT_ROOT` | 本仓库在 WSL 内的根路径 | `/home/你的用户名/insar-system` 或 `/mnt/d/coding/insar-system` |
| `INSAR_WSL_DISTRO` | WSL 发行版名称；**默认固定为 Ubuntu**，桥接仅使用该发行版，一般无需设置 | 需改用其他发行版时可设，如 `InsarUbuntu24` |

在 WSL **Ubuntu** 终端中执行 `echo $HOME` 得到用户名目录，再拼出路径，例如：`/home/john/insar-wsl/env_isce2.sh`。在 Windows 中设置（PowerShell）：`$env:INSAR_WSL_ENV_SCRIPT="/home/john/insar-wsl/env_isce2.sh"`，`$env:INSAR_WSL_PROJECT_ROOT="/home/john/insar-system"`。

## 7. 项目工作区（WSL 原生）

中间处理与结果均放在 WSL 原生文件系统，例如：

- 工作区根：`~/insar-projects`
- 某项目：`~/insar-projects/<项目名>/stack`（Stack work_dir）、`~/insar-projects/<项目名>/mintpy`（MintPy work_dir）

原始数据不拷贝，保留在 Windows 盘符；仅在第一步（解压/load_data）通过 `/mnt/d/...` 读取。

## 8. 导出环境供客户部署（可选）

在 WSL 内环境配置完成后，可在 **Windows**  PowerShell 中导出该发行版（建议使用唯一名称，避免与客户已有 “Ubuntu” 冲突）：

```powershell
wsl --export InsarUbuntu24 D:\backup\insar-wsl.tar
```

客户导入：

```powershell
wsl --import InsarUbuntu24 D:\WSL\InsarUbuntu24 D:\backup\insar-wsl.tar
```

在 Desktop 设置中将「WSL 发行版名称」配置为 `InsarUbuntu24` 即可。

## 9. 检查环境是否就绪

- **在 WSL 内**：执行 `bash scripts/wsl/check_env.sh`（需在项目根目录，即 WSL 内有一份仓库时），或手动运行：
  ```bash
  source ~/insar-wsl/env_isce2.sh   # 或 conda activate isce2
  python -c "import isce; print('ISCE2 OK')"
  python -c "import mintpy; print('MintPy OK')"
  ```
- **在 Windows 上**：双击或运行 `scripts\check_wsl_env.bat`，会通过 WSL 自动检查 ISCE2 与 MintPy 是否可导入，并提示 READY / NOT READY。

**未配置时自动配置**：运行 `scripts\ensure_wsl_env.bat`（或在 WSL 内运行 `bash scripts/wsl/ensure_env.sh`）。脚本会先检查环境；若未就绪，会自动执行 Miniconda + isce2 + mintpy 安装（与 `setup_isce2_ubuntu24.sh` 相同），然后再次检查。首次安装可能需要数分钟。

## 10. 离线部署：构建 WSL 镜像与部署向导

**适用场景**：用户机无网络或不允许在 WSL 内执行在线安装时，使用预导出的 WSL 镜像 + 部署向导完成环境部署。

### 10.1 在构建机上导出 WSL 镜像（有网络）

**一键导出（推荐）**：在项目根目录双击 **`packaging/export_wsl_image.bat`**（或运行 `powershell -File packaging/export_wsl_image.ps1`）。脚本会检测 WSL 与 Ubuntu、在 WSL 内自动执行 `scripts/wsl/ensure_env.sh`（若未配置则安装 Miniconda+ISCE2+MintPy），然后执行 `wsl --export`，输出到 **`dist/insar-wsl.tar`**。将 `dist/` 整份（含 InSAR Desktop、InSAR WSL Deploy Wizard、insar-wsl.tar）拷贝到离线环境即可。

**手动导出**（若需自定义发行版名或路径）：
1. 在 **Windows 构建机** 上安装 WSL2 与 Ubuntu（如 24.04）。
2. 在 WSL 内按本文档 §2–§6 配置 Miniconda、isce2、MintPy，并创建 `~/insar-wsl/env_isce2.sh`（可与 `scripts/wsl/env_isce2.sh` 一致）。建议使用**固定用户名**（如 `insar`），便于向导中固定写 `INSAR_WSL_ENV_SCRIPT=/home/insar/insar-wsl/env_isce2.sh`。
3. 在 **Windows PowerShell** 中导出（发行版名建议用专用名，避免与用户本机 Ubuntu 冲突）：
   ```powershell
   wsl --export Ubuntu D:\build\insar-wsl.tar
   ```
   若希望发行版名为 `InsarUbuntu24`，可先将 Ubuntu 复制为新发行版再导出，或导出后由客户以 `InsarUbuntu24` 之名导入（见下）。
4. 将 `insar-wsl.tar` 放入安装包或与「InSAR WSL 部署向导」同目录，供用户离线使用。

### 10.2 用户机：运行部署向导（离线）

1. 确保 Windows 已启用「适用于 Linux 的 Windows 子系统」且可运行 `wsl`（无需事先安装 Ubuntu，导入镜像即会创建发行版）。
2. 运行 **InSAR WSL 部署向导**（与 Desktop 同目录的 `InSAR WSL 部署向导.exe` 或 `python -m packaging.wsl_deploy_wizard`）。
3. 按向导选择：`insar-wsl.tar` 路径、导入目标目录（如 `D:\WSL\InsarUbuntu24`）；执行导入后，向导会写入 `wsl_config.env`（INSAR_WSL_DISTRO、INSAR_WSL_ENV_SCRIPT、INSAR_WSL_PROJECT_ROOT），Desktop 启动时自动加载。
4. 启动 InSAR Desktop 即可使用 WSL 处理；若未配置 WSL，Desktop 可提示用户先运行部署向导。

详见 `packaging/README.md` 与部署向导界面说明。

## 11. 参考

- ISCE2 官方：[README](https://github.com/isce-framework/isce2)、SCons/CMake 构建说明。
- MintPy：[installation.md](https://github.com/insarlab/MintPy/blob/main/docs/installation.md)。
- 本项目 WSL 迁移计划：`.cursor/plans/wsl2_isce2_migration_plan.md`。
