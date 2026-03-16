# 阶段 3：Backend 与本机 ISCE2 集成（Windows）

阶段 2 完成后，ISCE2 已安装到 `lib/isce2-main/install`。阶段 3 使 **Backend（FastAPI/Celery）在 Windows 本机** 能使用该安装运行 S1 处理，无需依赖 Docker 内的 ISCE2。

## 3.1 已完成

- **s1_processing_service.py**
  - 优先将 `lib/isce2-main/install/packages` 加入 `sys.path`（若存在），供本机使用已安装的 ISCE2。
  - 导入顺序：`isceobj` → `isce.components.isceobj` → `isce2.components.isceobj`（适配 install/packages 下的 isce2 布局）。
- **backend 测试**：`test_s1_processing.py`、`test_s1_integration.py` 增加对 `isce2.components.isceobj` 的导入回退，便于在本机通过测试。

## 3.2 本机运行 Backend 时的环境要求

在 Windows 上运行 API 或 Celery worker 并调用 ISCE2 时，需满足：

1. **Python**：使用与 ISCE2 扩展一致的 Python（阶段 2 使用 conda 的 **isce2-build** 环境）。
   - Anaconda：`C:\ProgramData\Anaconda3\envs\isce2-build\python.exe`
   - Miniconda3：`D:\env\miniconda3\envs\isce2-build\python.exe`
2. **PATH**：包含以下路径（顺序靠前），以便加载 .pyd 依赖的 DLL：
   - MSYS2 UCRT64：`d:\coding\insar-system\tools\msys64\ucrt64\bin`
   - isce2-build 的 `Library\bin` 与 `bin`
3. **PYTHONPATH**：必须包含：
   - 项目根目录：`d:\coding\insar-system`（以便 `import backend`）
   - ISCE2 安装包：`d:\coding\insar-system\lib\isce2-main\install\packages`（脚本或手动设置）
4. **Python/CRT 一致**：必须使用**编译 ISCE2 时所用的同一 conda 环境**。若用 Miniconda3 的 isce2-build 运行，而 ISCE2 是用 Anaconda 的 isce2-build 编译的，会报 `DLL load failed while importing StdOEL`。解决办法：用编译时的 Python 运行，或使用当前 env 重新编译 ISCE2（见阶段 2 文档）。

## 3.3 验证命令示例

使用 isce2-build 的 Python 并设置 PATH 后，在项目根目录执行：

```powershell
# 设置 PATH（UCRT64 + isce2-build）
$ucrt  = "d:\coding\insar-system\tools\msys64\ucrt64\bin"
$conda = "D:\env\miniconda3\envs\isce2-build"   # 或 C:\ProgramData\Anaconda3\envs\isce2-build
$env:Path = "$ucrt;$conda\Library\bin;$conda\bin;" + $env:Path
$env:PYTHONPATH = "d:\coding\insar-system;d:\coding\insar-system\lib\isce2-main\install\packages"
$env:PYTHONIOENCODING = "utf-8"

# 运行 backend 的 S1 处理测试
& "$conda\python.exe" -m backend.tests.test_s1_processing
```

或使用项目提供的脚本（会自动设置 PATH、PYTHONPATH、UTF-8 并选用已存在的 isce2-build）：

```powershell
.\scripts\run_phase3_verify.ps1
```

**验证结果说明**：脚本使用 isce2-build 环境（无 pydantic/celery），故「共享模型」「Celery 任务」导入失败属正常。若 **ISCE2 Sentinel1 导入** 报 `DLL load failed`，说明当前 Python 与编译 ISCE2 时所用环境不一致，请改用编译时的 conda 环境运行或重新用当前 env 编译 ISCE2。

## 3.4 与 Docker 的关系

- **Docker**：worker 使用镜像 `insar-ubuntu20`，其内已装 ISCE2，无需改镜像即可跑 S1 任务。
- **本机**：若希望在本机直接跑 API + worker（不启动 Docker），需按 3.2 使用 isce2-build 的 Python 并设置 PATH/PYTHONPATH；backend 会自动使用 `lib/isce2-main/install/packages` 下的 ISCE2。

## 3.5 后续可选（阶段 4 已实现）

- **阶段 4** 已提供本机 API/Worker 启动脚本与说明，见 `docs/windows-phase4.md`、`scripts/run_api_windows.ps1`、`scripts/run_worker_windows.ps1`。
- 使用真实 SAFE 数据跑一次 `run_s1_import_from_request` 或 `run_sentinel1_extract` 做端到端验证。
