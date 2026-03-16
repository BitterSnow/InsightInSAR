## Insight InSAR

Windows 原生的 InSAR 处理系统，包含本地桌面端（PySide6）、后端服务（FastAPI + Celery + Redis）以及与 ISCE2 / MintPy 集成的 InSAR 处理流水线，面向工程/生产环境的一站式形变监测工具。

### 核心特性

- **本地桌面应用**：基于 PySide6 的 B/S 风格桌面 UI，支持任务管理、ROI 选择、产品浏览和参数配置。
- **后端任务调度**：FastAPI 提供 REST API，Celery 负责异步调度长时间 InSAR 处理任务（与 Redis 协作）。
- **InSAR 处理流水线**：通过统一的 Python Facade 调用本机 ISCE2（CMake 构建的 .pyd）和 MintPy，完成从 SLC 导入到时序分析的流程。
- **工程化部署**：面向 Windows 单机部署，提供打包与运行脚本，可脱离 Docker 直接安装运行。
- **日志与监控**：任务进度、运行日志持久化到本地文件，桌面端可查看运行状态与错误信息。

### 技术栈总览

- **桌面端（desktop/）**
  - PySide6（Qt for Python）
  - Qt Widgets / QGraphicsView 等实现地图与图像可视化
  - 内嵌 Matplotlib / 图表控件，用于时序曲线与剖面显示

- **后端服务**
  - FastAPI：任务提交、状态查询、结果获取等 REST 接口
  - Celery：异步任务队列（长时间 ISCE2 / MintPy 处理）
  - Redis：Celery broker / backend（可根据部署环境调整）
  -（可选）PostgreSQL：项目与任务元数据持久化

- **InSAR 引擎**
  - ISCE2：通过 Python API 使用 CMake 构建的 .pyd 扩展（不依赖 Docker）
  - MintPy：时序形变分析与可视化产物生成
  - 统一 Facade：将复杂 InSAR 步骤包装成稳定的 Python 调用接口（如 `run_s1_slc_extract` 等）

### 目录结构（简要）

```
insar-system/
├── desktop/              # PySide6 桌面应用源码
├── config/               # 后端与处理流水线的配置文件
├── scripts/              # 开发 / 部署 / 运维脚本
├── packaging/            # Windows 打包与安装相关脚本与配置
├── build/                # 构建中间目录（可清理）
├── dist/                 # 打包产物（如安装包、可执行文件）
├── docs/                 # 文档（安装、架构、阶段规划等）
├── logs/                 # 运行日志（本地调试与生产排障）
├── .cursor/              # Cursor AI 配置（本地规划与技能，不推到 GitHub）
├── .venv/                # Python 虚拟环境（本地）
└── README.md             # 当前文件
```

更多详细说明可参考：`docs/installation_and_deployment.md` 以及阶段性 Windows 安装文档（如 `docs/windows-phase*.md`）。

### 快速开始（开发环境）

1. **准备环境**
   - Windows 10/11
   - Python 3.10+（推荐使用 Miniconda/Conda 管理环境）
   - ISCE2 + MintPy 已按 `docs/windows-phase*.md` 配置完成，并能在当前 Python 环境中导入。

2. **创建与激活虚拟环境**

   ```bash
   # 建议在 Anaconda Prompt / PowerShell 中执行（示例）
   conda create -n insight-insar python=3.10
   conda activate insight-insar

   # 进入项目目录
   cd d:\coding\insar-system
   ```

3. **安装依赖**

   ```bash
   # 如果项目中提供 requirements / 环境文件，请使用相应命令
   pip install -r packaging/requirements.txt
   ```

4. **启动后端服务与桌面端**

   具体启动命令请参考 `docs/installation_and_deployment.md`：
   - 启动 FastAPI（开发模式）：`uvicorn backend.main:app --reload`
   - 启动 Celery worker：`celery -A backend.celery_app worker -l info`
   - 启动桌面应用：运行 `python -m desktop` 或对应启动脚本（以实际实现为准）。

### 架构概览

- 桌面端通过 HTTP（及可选的 WebSocket）与本地 FastAPI 通信，完成：
  - InSAR 任务参数配置与提交
  - 任务状态轮询 / 进度订阅
  - 结果文件路径与元数据获取
- FastAPI 将长时间任务下发至 Celery，由 Celery 在同一台机器上调用 ISCE2 / MintPy Python API 完成计算，并将中间与最终结果写入本地磁盘。
- 所有路径与数据目录均围绕本机单机部署进行设计，适配 Windows 文件系统路径与权限。

### License

MIT
