<!-- updated: 2026-06-02, sources: README.md, packaging/README.md, docs/installation_and_deployment.md, desktop/app/main_window.py -->

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

## 第二部分 安装与 WSL 部署

现在开始部署。  
第一步，进入 InSAR WSL Deploy Wizard 目录，双击运行部署向导。  
向导打开后，会先检查 WSL 是否可用。这里如果失败，常见原因是 WSL 没启用、系统需要重启，或者当前机器没有安装可用的 WSL 组件。

检查通过后，选择 insar-wsl.tar。  
这个 tar 是 WSL 镜像文件，不是普通数据文件。它的作用是把已经配置好的 Ubuntu 计算环境导入到当前机器。  
接着选择导入目标目录。这个目录用来存放 WSL 发行版文件，建议放在空间充足的磁盘，不要放到临时目录。

点击导入后，向导会执行 wsl --import。  
导入完成后，向导会生成运行配置，主要包括 WSL 发行版名称、环境脚本路径，以及项目根目录对应的 WSL 路径。  
这些配置会写入 wsl_config.env。主程序启动时会自动读取它，所以正常情况下用户不需要手动设置环境变量。

部署完成后，再打开 InSAR Desktop 主程序。  
顺序要记住：先部署 WSL，再启动桌面端。  
如果你先打开桌面端，也可以看到界面，但一旦提交计算任务，就可能因为找不到 WSL 环境或项目根目录而失败。

如果是开发环境，不一定要用导入向导。  
也可以在 WSL 里按文档配置 ISCE2 和 MintPy，然后用 scripts/start_desktop_wsl.bat 启动。这个脚本会设置 INSAR_USE_WSL、INSAR_WSL_PROJECT_ROOT 等变量，再启动桌面端。  
但如果是给别人交付，尤其是离线机器，推荐使用部署向导加 insar-wsl.tar。

这里补充一个更新原则。  
Insight InSAR 采用环境和代码分离。WSL 镜像主要放 Ubuntu、ISCE2、MintPy 这些低频更新的环境；业务代码放在 Windows 安装根目录。  
所以如果只是更新 backend、scripts 或 MintPy 处理脚本，通常覆盖安装根目录下的对应文件夹即可，不需要重新导入 WSL 镜像。只有计算环境本身升级时，才需要重新导出新的 tar。

## 第三部分 从新建工程到 Sentinel-1 导入

下面进入软件使用。  
打开主程序后，第一件事是新建工程。  
在菜单里选择文件，新建工程。填写工程名称，雷达数据类型选择 Sentinel-1，然后选择一个 Windows 绝对路径作为项目路径。  
这里建议路径简单一点，比如 D 盘或专门的数据盘下面的项目目录。不要使用权限复杂的系统目录。

工程建好后，左侧会出现工程节点。  
下一步是定义工作区，也就是本次处理的空间范围。  
可以通过界面输入范围，也可以在后续 Stack 配置里导入 KML，让软件读取多边形边界并自动填入 SNWE 范围。  
工作区不是装饰信息，它会影响 subswath 判断、DEM 范围和后续处理区域。

然后准备基础数据。  
Sentinel-1 SLC 数据可以是 zip，也可以是 .SAFE 目录。实际使用时更推荐把同一项目的数据放到一个雷达数据目录里，软件会扫描目录下的 zip 和 SAFE。  
轨道文件放到轨道目录。Aux 文件放到 Aux 目录。DEM 可以选择已有文件，也可以使用软件里的 DEM 制作功能。

先看 DEM 制作。  
在数据导入或 Stack 配置界面里，点击 DEM 制作。  
界面会让你选择 DEM 原始瓦片目录和输出目录，并填写处理范围。  
如果已经定义了工作区和 SAFE 数据，可以点击根据工作区与 Swath 更新范围。这样软件会根据实际需要处理的 swath 计算 DEM 覆盖范围。  
然后点击开始制作。后台会在 WSL 中调用 ISCE2 的 dem.py 拼接 DEM。日志里能看到瓦片检查、下载或拼接过程。

DEM 成功后，回到数据导入界面。  
填写 SAFE 数据目录、轨道目录、DEM 路径、Aux 目录、极化方式和 swath。  
如果你已经定义了工作区，可以点击根据处理范围自动填充 swath。软件会读取 Sentinel-1 annotation，判断 IW1、IW2、IW3 哪些和工作区相交。  
这一步很实用，因为只处理需要的 subswath，可以减少不必要的计算。

参数确认后，可以先点保存到工程。  
这样下次打开项目时，路径和参数可以自动回填，不需要每次重新选择。  
然后点击开始导入。导入会在 WSL 中调用 ISCE2 的 Sentinel1 解析和 extractImage，输出 SLC/VRT 结果。  
运行时重点看日志：如果失败，先检查 SAFE 路径、轨道目录、DEM 路径、Aux 目录是否能被 WSL 访问。尤其是数据在网络盘或非系统盘时，要注意 WSL 内是否已经挂载对应盘符。

## 第四部分 Stack 流程、MintPy 流程与结果导出

S1 数据准备好后，进入 Stack 流程。  
在工程界面打开 Stack 流程配置。这里需要填写工作目录、SLC 数据目录、DEM、轨道目录、Aux 目录、处理范围和参考日期等参数。  
如果有 KML，可以直接导入 KML 生成范围。  
确认后点击初始化流程。

初始化流程会在 WSL 中运行 stackSentinel.py，生成 configs 和 run_files。  
软件会解析 run_xx，把它们显示成可以逐步执行的流程。  
后面你可以运行当前步、从本步运行，或者全线运行。  
第一次跑建议不要急着全线运行，先从初始化和前几步开始，确认 reference、merged、geom_reference 这些目录逐步生成。

Stack 运行时，日志非常关键。  
如果某一步很久没有结束，先不要立刻判断为卡死。topsStack 的某些步骤本来就比较耗时，尤其是参考景解包、几何、干涉和解缠相关步骤。  
真正需要警惕的是日志里出现路径不可访问、找不到 zip、找不到 DEM、找不到 stackSentinel.py，或者 WSL 环境没有激活成功。

Stack 跑到可以进入时间序列分析后，点击进入时间序列。  
软件会打开 MintPy 工作目录配置。通常 MintPy 工作目录放在 stack 输出目录下面的 mintpy 文件夹。  
初始化时，系统会创建 smallbaselineApp.cfg，并把 ISCE topsStack 产物路径写进去，比如 reference、baselines、merged/interferograms、merged/geom_reference 等。

进入 MintPy 流程界面后，你会看到一张步骤表。  
常用流程包括加载数据、修改网络、设置参考点、解缠误差校正、网络反演、潮汐或大气相关校正、去斜、地形残差校正、速率估计和地理编码。  
每一步都可以单独运行，也可以从某一步继续往后跑。  
建议第一次处理时逐步运行，确认每一步的输出和日志，再考虑批量跑完。

MintPy 失败时，优先看 smallbaselineApp.cfg 里的路径。  
最常见的问题不是算法本身，而是模板里某个输入文件路径不对，或者 Stack 产物还没有跑到 MintPy 需要的阶段。  
如果 load_data 失败，先看 reference、baselines、interferograms、geom_reference 是否存在。  
如果后面的校正步骤失败，再看对应外部数据、参数开关和天气数据配置。

处理完成后，可以打开产品查看界面检查结果。  
如果需要把 MintPy 的 velocity 和 timeseries 输出给 GIS 使用，可以打开工具菜单里的 MintPy 转矢量。  
选择 velocity 文件、timeseries 文件和输出格式，可以生成 GeoPackage 或 Shapefile 点图层。  
这样后续就能在 QGIS 或其他 GIS 软件里叠加分析。

最后给第一次使用的建议。  
不要一开始就拿最大区域和最多景数据测试。  
先选一个小范围、少量影像，跑通 DEM、S1 导入、Stack 初始化、MintPy load_data 这几步。  
只要这条链路通了，再扩大数据量。这样排错成本最低，也最容易判断问题来自环境、路径、数据还是参数。

## 结尾

这期视频我们按实操顺序走完了 Insight InSAR 的基本用法。  
重点再重复一遍：Windows 端负责操作，WSL 端负责计算；先部署 WSL，再启动桌面；先小样本跑通链路，再扩大处理规模。  

如果你在使用中遇到问题，优先保留三类信息：当前工程路径、wsl_config.env 配置，以及失败步骤前后的日志。  
有了这些信息，绝大多数问题都能比较快定位。  

感谢观看，下一期可以继续讲一个完整 Sentinel-1 示例项目，从数据准备一直跑到 MintPy 速率结果。
