## Insight InSAR

Windows 桌面 + WSL InSAR 处理的一站式形变监测系统：本地桌面端（PySide6）与后端（FastAPI + Celery + Redis）运行在 Windows，**无网页前端依赖**；所有 InSAR 计算（ISCE2 / MintPy）仅在 WSL 内执行，无需在 Windows 上安装或构建 ISCE2。

### 核心特性

- **本地桌面应用**：基于 PySide6 的桌面 UI，支持任务管理、ROI 选择、产品浏览和参数配置。
- **非 Web 前端架构**：交互入口是 Desktop 客户端（非浏览器页面），后端仅作为本机 API 与异步调度服务。
- **后端任务调度**：FastAPI 提供 REST API，Celery 异步调度长时间任务，与 Redis 协作。
- **InSAR 仅走 WSL**：S1 导入、topsStack、MintPy 等全部通过 `wsl` 命令在 WSL 中调用 ISCE2 / MintPy，桌面与后端只做参数与进度桥接。
- **工程化部署**：Windows 单机部署，提供「InSAR WSL 部署向导」导入 WSL 镜像与配置，打包后可脱离 Docker 运行。
- **日志与监控**：任务进度与运行日志落盘，桌面端可查看状态与错误信息。

### 技术栈总览

- **桌面端（desktop/）**
  - PySide6（Qt for Python）
  - Qt Widgets / QGraphicsView 等实现地图与图像可视化
  - 内嵌 Matplotlib / 图表控件，用于时序曲线与剖面显示

- **后端服务**
  - FastAPI：供 Desktop 调用的本机 REST 接口（任务提交、状态查询、结果获取）
  - Celery：异步任务队列（将 InSAR 步骤下发至 WSL 执行）
  - Redis：Celery broker / backend

- **InSAR 引擎（仅 WSL）**
  - ISCE2：在 WSL 内通过 Python API 使用（Ubuntu 等环境下安装/构建）
  - MintPy：在 WSL 内完成时序形变分析与产物生成
  - 桥接方式：后端通过 `backend.services.wsl_runner` 调用 `wsl`，在 WSL 中执行 `backend.scripts.run_*_wsl` 等入口

### 目录结构（简要）

```
InsightInSAR/
├── desktop/              # PySide6 桌面应用源码
├── config/               # 后端与处理流水线的配置文件
├── scripts/              # 开发 / 部署 / 运维脚本
├── packaging/            # Windows 打包与安装相关脚本与配置
├── build/                # 构建中间目录（可清理）
├── dist/                 # 打包产物（如安装包、可执行文件）
├── manual/               # 操作说明书（PDF、HTML、截图）
├── logs/                 # 运行日志（本地调试与生产排障）
├── .venv/                # Python 虚拟环境（本地）
└── README.md             # 当前文件
```

安装与离线交付说明见：`packaging/README.md`。操作说明书见：`manual/README.md`。

### 快速开始（开发环境）

1. **环境要求**
   - Windows 10/11，已启用 WSL 2
   - 本机 Python 3.10+（用于运行桌面与后端，**不需**在 Windows 上安装 ISCE2）
   - WSL 内已配置好 ISCE2 与 MintPy，并设置 `INSAR_USE_WSL=1`、`INSAR_WSL_PROJECT_ROOT` 等（见 `packaging/README.md`；可通过「InSAR WSL 部署向导」或 `scripts/start_desktop_wsl.bat` 写入配置）

2. **创建与激活虚拟环境**

   ```bash
   conda create -n insight-insar python=3.10
   conda activate insight-insar
   git clone https://github.com/BitterSnow/InsightInSAR.git
   cd InsightInSAR
   ```

3. **安装依赖**

   ```bash
   pip install -r packaging/requirements.txt
   ```

4. **启动方式（WSL 模式）**

   - 推荐：使用 `scripts/start_desktop_wsl.bat` 启动（会加载 WSL 配置并启动桌面），或先设置 `INSAR_USE_WSL=1` 与 `INSAR_WSL_PROJECT_ROOT` 后启动后端与桌面。
   - 启动 FastAPI：`uvicorn backend.app.main:app --reload`
   - 启动 Celery worker：`celery -A backend.app.celery_app worker -l info`
   - 启动桌面：`python -m desktop`

### 架构概览

- 桌面端通过 HTTP 与本地 FastAPI 通信：提交任务、轮询状态、获取结果路径与元数据。
- FastAPI 将 InSAR 任务交给 Celery；Celery 通过 **wsl_runner** 在 WSL 内执行 `run_s1_extract_wsl`、`run_stack_wsl`、`run_mintpy_wsl` 等，**不在 Windows 上直接调用 ISCE2/MintPy**。
- 数据与工作目录可为 Windows 路径；后端在调用 WSL 前将所需路径转换为 WSL 路径，结果仍可从 Windows 访问。

### License

MIT
