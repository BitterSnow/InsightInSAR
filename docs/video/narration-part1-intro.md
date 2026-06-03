## 片头

大家好，这期视频直接讲 Insight InSAR 怎么用。  
不讲太多概念铺垫，我们按真实操作顺序走一遍：先确认安装包，导入 WSL 环境，启动桌面端；然后新建工程、定义工作区、准备 DEM、导入 Sentinel-1 数据、跑 Stack，最后进入 MintPy 做时间序列分析。  

看完这期，你至少要能判断三件事。  
第一，软件哪一部分在 Windows 上运行，哪一部分在 WSL 里运行。  
第二，安装完成后怎么确认计算链路真的可用。  
第三，第一次处理 Sentinel-1 数据时，每一步应该点哪里、填什么、看什么日志。

## 第一部分 软件边界与准备工作

先看一句最重要的话：Insight InSAR 的界面在 Windows，核心计算在 WSL。  
桌面程序负责工程管理、路径选择、参数配置、流程按钮和日志显示；ISCE2、topsStack、MintPy 这些计算工具在 WSL 的 Ubuntu 环境里执行。  
所以后面排错时不要只看 Windows 界面。任务失败时，要重点看 WSL 环境、路径映射、输入数据和日志。

开始安装前，先确认你手里有三个交付物。  
第一个是 InSAR Desktop，也就是主程序目录。  
第二个是 InSAR WSL Deploy Wizard，也就是 WSL 部署向导目录。  
第三个是 insar-wsl.tar，这是提前导出的 WSL 镜像，里面包含 Ubuntu、ISCE2 和 MintPy 运行环境。  

这里不要省略第三项。  
如果没有 insar-wsl.tar，桌面程序也许还能打开，但后面的 S1 导入、DEM 制作、Stack 和 MintPy 都跑不起来。界面能打开，只能说明 Windows 端正常，不能说明 WSL 计算环境已经可用。

再检查 Windows 侧前提。  
系统建议使用 Windows 10 或 Windows 11，并启用 WSL2。  
可以打开 PowerShell，运行 wsl -l -v。  
如果能看到 Ubuntu 或已经导入的发行版，并且版本是 2，说明基础条件基本具备。  
如果这里就报错，先处理 WSL，而不是急着打开 Insight InSAR。

最后看目录结构。  
推荐把主程序目录、部署向导目录和 insar-wsl.tar 放在同一个安装根目录下面。  
这样部署向导写入配置时，可以把安装根目录转换成 WSL 路径，后续 WSL 就能通过 /mnt 访问 Windows 侧的 backend、scripts 和相关代码。
