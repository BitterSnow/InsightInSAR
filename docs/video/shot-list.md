# Insight InSAR 教学视频 — 实操分镜清单

| 镜号 | 解说重点 | 画面建议 | 时长(秒) |
|------|----------|----------|----------|
| 01 | 片头：本期按真实流程讲，不做概念长铺垫 | 标题页 + 软件 Logo | 20 |
| 02 | Windows 负责界面，WSL 负责计算 | README 或简单三栏图：Desktop / WSL / ISCE2+MintPy | 35 |
| 03 | 检查三件交付物 | 资源管理器展示安装根目录：Desktop、Deploy Wizard、insar-wsl.tar | 35 |
| 04 | 检查 WSL2 | PowerShell 执行 `wsl -l -v` | 30 |
| 05 | 运行部署向导 | 双击 `InSAR WSL Deploy Wizard.exe`，展示 WSL 检查页 | 40 |
| 06 | 选择 tar 和导入目录 | 向导中选择 `insar-wsl.tar`、目标目录 | 60 |
| 07 | 导入并写入配置 | 向导进度页；可切到 `wsl_config.env` 展示关键字段 | 50 |
| 08 | 启动桌面端 | 双击 `InSAR Desktop.exe`，进入主界面 | 30 |
| 09 | 新建工程 | 文件 -> 新建工程；填写名称、Sentinel-1、项目路径 | 60 |
| 10 | 定义工作区 | 展示工程节点、地图/工作区输入或 KML 导入入口 | 50 |
| 11 | 准备基础数据 | 展示 SLC、Orbit、Aux、DEM 目录结构 | 45 |
| 12 | DEM 制作 | 打开 DEM 制作面板，选择瓦片目录、输出目录、更新范围、开始制作 | 80 |
| 13 | S1 导入配置 | 打开数据导入，填写 SAFE、Orbit、DEM、Aux、极化和 swath | 70 |
| 14 | 自动 subswath | 点击根据处理范围自动填充；展示 IW1/IW2/IW3 结果 | 45 |
| 15 | 开始导入并看日志 | 点击开始导入；展示日志、SLC/VRT 输出目录 | 70 |
| 16 | Stack 初始化 | 打开 Stack 配置，填写工作目录、SLC、DEM、Orbit、Aux、范围、参考日期 | 80 |
| 17 | Stack 按步运行 | 流程界面：运行当前步、从本步运行、全线运行；展示 run_xx 状态 | 80 |
| 18 | 进入 MintPy | 点击进入时间序列，初始化 mintpy 工作目录和 cfg | 60 |
| 19 | MintPy 步骤表 | 展示 load_data、modify_network、invert_network、velocity、geocode 等步骤 | 70 |
| 20 | 结果查看与转矢量 | 产品查看；工具 -> MintPy 转矢量，选择 velocity/timeseries 和输出格式 | 65 |
| 21 | 排错总结 | 展示日志目录、工程路径、wsl_config.env 三类信息 | 35 |
| 22 | 片尾 | 标题页或主界面停留 | 20 |

**合计粗剪时长**：约 16 到 20 分钟。  
建议录制时每个功能点保留 2 到 3 秒停顿，后期剪辑时再压缩空白。
