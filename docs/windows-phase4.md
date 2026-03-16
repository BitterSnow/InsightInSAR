# 阶段 4：桌面端直连 ISCE（无 API 层）

阶段 3 完成后，Backend 已能使用本机安装的 ISCE2。阶段 4 采用 **桌面端直接调用 ISCE 处理函数** 的方式：用户仅需启动桌面程序，无需 FastAPI、Celery 或 Redis，即可完成工程管理与 Sentinel-1 导入（run_1），实现「单机桌面软件」体验。

## 4.1 架构说明

- **桌面端**（PySide6）为唯一用户入口；工程列表与当前项目保存在本机（项目根目录下 `desktop_projects.json`、`desktop_current_project.txt`）。
- **S1 导入**：通过菜单「项目」→「Sentinel-1 导入」打开配置对话框，填写 SAFE ZIP、轨道目录、DEM、Aux 等路径后点击「开始导入」，桌面进程在 **QThread** 中直接调用 `backend.services.s1_processing_service.run_s1_import_from_request`，通过 `progress_callback` 与 Qt 信号在界面中更新进度条与日志。
- **不再依赖**：无需先启动 API、Worker、Redis；`shared_models` 与 `s1_processing_service` 作为库被桌面端引用。

## 4.2 前置条件

- **阶段 2/3**：ISCE2 已安装到 `lib/isce2-main/install`，且与 conda **isce2-build** 环境一致（见 `docs/windows-phase3.md`）。
- **运行桌面**：必须使用 **isce2-build** 的 Python 启动桌面（以便加载 ISCE2 扩展），并设置 PATH（MSYS2 UCRT64 + conda）、PYTHONPATH（项目根 + `lib/isce2-main/install/packages`）。
- **桌面依赖**：在 isce2-build 中安装 `desktop/requirements-isce.txt`（PySide6、pydantic、geopandas、shapely 等）。

## 4.3 环境准备（isce2-build 安装桌面依赖）

在 isce2-build 环境中执行一次：

```powershell
# 项目根目录；Miniconda3 示例
D:\env\miniconda3\envs\isce2-build\python.exe -m pip install -r desktop\requirements-isce.txt
```

Anaconda 用户将路径改为 `C:\ProgramData\Anaconda3\envs\isce2-build\python.exe`。

## 4.4 启动桌面

双击或在终端运行：

```
scripts\start_desktop.bat
```

脚本自动检测 `.venv`（优先，用于 PySide6）或 `isce2-build` conda 环境（回退），设置 `PYTHONPATH`、`PYTHONIOENCODING` 等环境变量，然后运行 `python -m desktop.main`。启动后即可：

- 新建/打开/编辑工程（数据存于本地 `project_store`）；
- 通过「项目」→「Sentinel-1 导入」配置并执行 run_1，在对话框内查看进度与日志。

## 4.5 验证

1. 运行 `scripts\start_desktop.bat`，确认桌面窗口打开无报错。
2. 新建工程，选择 Windows 路径，确认工程出现在侧栏。
3. 打开「Sentinel-1 导入」，填写测试路径（或真实 SAFE/轨道/DEM），点击「开始导入」，确认进度条与日志更新；若 ISCE2 加载失败，请检查 Python 与编译 ISCE2 时所用环境一致（见阶段 3 文档）。

### 若出现「DLL load failed while importing QtWidgets」或「importing Shiboken」

- **原因**：通常缺少 **Visual C++ Redistributable**（PySide6/Qt 依赖）。
- **处理**：安装 [VC++ 2015–2022 x64 运行库](https://aka.ms/vs/17/release/vc_redist.x64.exe)，安装后若仍报错可重启系统再试。

### 若出现「DLL load failed while importing StdOEL」

- **原因**：桌面未用「能加载 ISCE2」的 Python 启动，或当前 Python 与编译 ISCE2 时使用的 conda 环境不一致。
- **处理**：
  1. **必须用脚本启动**：双击 `scripts\start_desktop.bat` 或在终端执行，不要用 IDE 或 `.venv` 直接运行 `desktop.main`。
  2. 若已用脚本仍报错：改用**编译 ISCE2 时所用的** conda 环境（如当时用 Anaconda 的 isce2-build 编译，就需用该环境的 Python 运行脚本）；或使用当前 Miniconda3 的 isce2-build **重新编译 ISCE2**（见阶段 2/3 文档）。

## 4.6 与 API/Worker 的关系

- **主流程**：桌面直连 ISCE，**不需要** 启动 API、Worker、Redis。
- **可选**：若需单独调试后端接口或 Celery 任务，可继续使用 `scripts/run_api_windows.ps1`、`scripts/run_worker_windows.ps1`（需 Redis）；详见阶段 3 及脚本内注释。
- **Docker**：`docker-compose --profile full up` 仍在容器内提供 API + Worker，与桌面直连方案并行可选。

## 4.7 后续可选

- 使用真实 SAFE 数据做一次端到端 S1 导入验证。
- 桌面端增加「已导入数据」列表、按日期查看强度图等（与 plan.txt 描述一致）。

## 4.8 Stack 流程初始化

### 已修复：退出码 3228369023（ silent 崩溃）

若此前出现 **Return code: 3228369023**、无 stdout/stderr，原因已定位并修复：

- **原因**：子进程使用的 **conda Library 路径错误**（误用 `envs\Library\bin` 而非 `envs\isce2-build\Library\bin`），导致加载时触发 STATUS_STACK_BUFFER_OVERRUN。
- **修复**：`stack_processing_service` 与相关脚本中已改为 `conda_lib = os.path.join(conda_bin, "Library", "bin")`；子进程使用**隔离 PATH**（仅 UCRT64 + conda + SystemRoot，不继承桌面 .venv），避免 DLL 混用。

### 若出现「DLL load failed while importing StdOEL: 找不到指定的模块」

StdOEL.pyd 是用 **MinGW/UCRT64** 编译的，运行时需要 `libgcc_s_seh-1.dll`、`libstdc++-6.dll`、`libwinpthread-1.dll` 等。本机若没有这些 DLL（VC++ 运行库无法替代），需按下面任选一种方式提供：

**方式一：用 MSYS2 安装 UCRT64 运行库，并让程序使用该目录**

1. 若尚未安装 [MSYS2](https://www.msys2.org/)，先安装（默认装到 `C:\msys64`）。
2. 从开始菜单打开 **「MSYS2 UCRT64」**（不要用 MSYS2 MSYS 或 MINGW64）。
3. 在终端中执行：
   ```bash
   pacman -S mingw-w64-ucrt-x86_64-gcc-libs
   ```
   输入 `Y` 确认。安装后 `C:\msys64\ucrt64\bin` 下会有上述 DLL。
4. **二选一**：
   - **A**：把 `C:\msys64\ucrt64\bin` 下所有 `.dll` 复制到项目的 `tools\msys64\ucrt64\bin`（若目录不存在则先建好），程序会优先使用项目内该目录。
   - **B**：不复制，在启动桌面前设置环境变量，指向 MSYS2 的 ucrt64\bin。例如在运行 `start_desktop.bat` 前，在 CMD 中执行：
     ```bat
     set INSAR_UCRT64_BIN=C:\msys64\ucrt64\bin
     scripts\start_desktop.bat
     ```

**方式二**：用**当前 Miniconda 的 isce2-build** 按阶段 2/3 文档**重新编译 ISCE2**，并确保编译时使用的 MinGW/UCRT64 运行库在运行时可被找到（同上，需有上述 DLL 在 PATH 或项目 `tools\msys64\ucrt64\bin`）。

程序会优先使用环境变量 **INSAR_UCRT64_BIN** 指定的目录作为 UCRT64 bin；未设置时使用项目下的 `tools\msys64\ucrt64\bin`。

### 诊断与手动测试

- **工作目录日志**：每次初始化在工作目录下追加 `stack_init.log`（含 PATH、命令、stdout、stderr、退出码）。
- **独立启动脚本**（与桌面环境隔离，便于在 CMD 下复现）：  
  `D:\env\miniconda3\envs\isce2-build\python.exe scripts\run_stack_sentinel_standalone.py -w <工作目录> -s <SLC目录> -o <轨道> -a <Aux> -d <DEM> ...`  
  参数与「Stack 流程配置」中一致，输出在控制台。

### DEM 换路径后报错（如 `/media/.../dem.vrt' does not exist`）

- **原因**：DEM 在 Linux 下用 dem.py 等脚本拼接时，同级 `.xml` 里会记录当时的绝对路径（如 `/media/bush/process/.../dem.dem.vrt`）。拷贝到 Windows 或换目录后，ISCE2 仍按 XML 里的路径找文件，导致报错。
- **处理**：topsStack 已做路径规范化：`topo.py` 与 `geocodeIsce.py` 在 `load(DEM.xml)` 后会强制把 `filename`、`_extraFilename`、`metadatalocation` 设为**当前传入的 DEM 路径**（如 `D:\...\dem.dem` 与同目录的 `.vrt`/`.xml`），不再依赖 XML 中的旧路径。请确保 DEM 目录下同时存在 `.dem`、`.dem.xml`，若使用 VRT 则还需同名的 `.dem.vrt`（且 VRT 内用相对路径引用 .dem 即可）。

### 若出现「Error. GDAL is an unrecognized Interleaved Scheme」/「InterleavedFactory.cpp … Exiting」

- **原因**：Windows 下用 MinGW 编译 ISCE2 时，为规避与 conda GDAL 的 ABI 冲突，CMake 会关闭 C++ 端的 GDAL 支持（`HAVE_GDAL=0`）。topo 等步骤通过 VRT 打开 DEM 时会请求 scheme=`GDAL`，C++ 未编译该分支即报错退出。
- **处理**：项目已在 Python 端做回退：当需要以 GDAL 方式打开影像时，自动用 Python 的 `osgeo.gdal` 将文件转为临时 BSQ 再交给 C++，无需重新编译 ISCE2。请确保 **isce2-build** 环境中已安装 `gdal` 与 `numpy`（`conda install gdal numpy`）。若仍报错，检查报错栈是否在 `DataAccessorPy.py` 的 `_gdal_to_bsq_temp`，并确认 DEM/VRT 路径可读。

### 常见失败信息（步骤失败时日志与弹窗会显示完整 stdout/stderr）

- **NODATA: No bursts to extract**：表示在给定 bbox/ROI 裁剪后没有剩余 burst，即范围与参考景/从景数据无重叠或设置不当。可检查「Stack 流程配置」中的范围（bbox_snwe）、参考景日期与 SLC 数据是否覆盖该区域。
