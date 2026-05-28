"""
MintPy 参数分组与元数据定义。
包含每个参数的类型、默认值、有效值范围、中文说明等。

数据来源：
- 默认值来自 MintPy-main/src/mintpy/defaults/smallbaselineApp_auto.cfg
- 注释来自 MintPy-main/src/mintpy/defaults/smallbaselineApp.cfg
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal


@dataclass
class ParamMeta:
    """单个参数的元数据"""

    key: str  # 配置键名 (mintpy.xxx.xxx)
    zh_name: str  # 中文显示名
    zh_desc: str  # 中文详细说明
    type: Literal["float", "int", "enum", "yes_no_auto", "path", "text", "date_list", "bbox"]
    default: str = "auto"
    auto_value: str = ""  # "auto" 解析到的真实值（用于 tooltip）
    unit: str = ""  # 单位
    min_val: float | None = None
    max_val: float | None = None
    valid_values: List[str] | None = None
    path_type: Literal["file", "dir"] | None = None  # 仅用于 path 类型
    pattern: str = ""  # 文件匹配模式 (仅用于 path 类型)
    section: str = ""  # 对应处理步骤
    advanced: bool = False  # 是否为高级参数
    allow_auto: bool = False  # 是否允许用户选择 "auto"


@dataclass
class ParamGroup:
    """参数分组"""

    group_id: str  # 分组ID
    zh_name: str  # 分组中文名
    zh_desc: str  # 分组说明
    section_order: int  # 在配置文件中的顺序
    params: List[ParamMeta] = field(default_factory=list)
    collapsible: bool = False  # UI是否可折叠
    default_expanded: bool = True  # 默认是否展开


# 步骤ID到分组的映射
STEP_TO_GROUPS: dict[str, List[str]] = {
    "load_data": ["compute", "load"],
    "modify_network": ["network"],
    "reference_point": ["reference"],
    "correct_unwrap_error": ["unwrap"],
    "invert_network": ["invert"],
    "correct_SET": ["set"],
    "correct_ionosphere": ["ionosphere"],
    "correct_troposphere": ["troposphere"],
    "deramp": ["deramp"],
    "correct_topography": ["topography"],
    "residual_RMS": ["rms"],
    "reference_date": ["ref_date"],
    "velocity": ["velocity"],
    "geocode": ["geocode", "output"],
}

# 核心参数分组定义
PARAM_GROUPS: List[ParamGroup] = [
    # ==================== 计算资源 ====================
    ParamGroup(
        group_id="compute",
        zh_name="计算资源",
        zh_desc="内存与并行计算配置",
        section_order=1,
        default_expanded=True,
        params=[
            ParamMeta(
                key="mintpy.compute.maxMemory",
                zh_name="最大内存",
                zh_desc="最大内存分配量（GB），建议不超过系统可用内存的80%",
                type="float",
                default="4",
                auto_value="4",
                unit="GB",
                min_val=0.1,
                max_val=256.0,
                section="compute",
            ),
            ParamMeta(
                key="mintpy.compute.cluster",
                zh_name="计算集群",
                zh_desc="并行计算集群类型，none 为单机运行",
                type="enum",
                default="none",
                auto_value="none",
                valid_values=["local", "slurm", "pbs", "lsf", "none"],
                section="compute",
            ),
            ParamMeta(
                key="mintpy.compute.numWorker",
                zh_name="工作进程数",
                zh_desc="并行工作进程数量，all 使用全部核心，80% 使用80%核心",
                type="text",
                default="4",
                auto_value="4",
                section="compute",
            ),
        ],
    ),
    # ==================== 数据加载 ====================
    ParamGroup(
        group_id="load",
        zh_name="数据加载",
        zh_desc="输入数据路径与加载选项",
        section_order=2,
        default_expanded=True,
        params=[
            ParamMeta(
                key="mintpy.load.processor",
                zh_name="处理器类型",
                zh_desc="InSAR处理软件类型，决定数据加载方式",
                type="enum",
                default="isce",
                auto_value="isce",
                valid_values=["isce", "aria", "hyp3", "gmtsar", "snap", "gamma", "roipac", "nisar"],
                section="load_data",
            ),
            ParamMeta(
                key="mintpy.load.autoPath",
                zh_name="自动路径",
                zh_desc="使用预定义的自动路径模式查找ISCE标准文件",
                type="yes_no_auto",
                default="no",
                auto_value="no",
                section="load_data",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.load.updateMode",
                zh_name="增量更新",
                zh_desc="已加载完成时跳过重新加载，节省时间",
                type="yes_no_auto",
                default="yes",
                auto_value="yes",
                section="load_data",
            ),
            # 文件路径参数
            ParamMeta(
                key="mintpy.load.metaFile",
                zh_name="元数据文件",
                zh_desc="ISCE metadata XML文件路径",
                type="path",
                path_type="file",
                pattern="*.xml",
                section="load_data",
            ),
            ParamMeta(
                key="mintpy.load.baselineDir",
                zh_name="基线目录",
                zh_desc="基线文件目录路径",
                type="path",
                path_type="dir",
                section="load_data",
            ),
            ParamMeta(
                key="mintpy.load.unwFile",
                zh_name="解缠相位文件",
                zh_desc="解缠干涉图路径模式，支持通配符",
                type="path",
                path_type="file",
                pattern="*.unw",
                section="load_data",
            ),
            ParamMeta(
                key="mintpy.load.corFile",
                zh_name="相干性文件",
                zh_desc="相干性图路径模式",
                type="path",
                path_type="file",
                pattern="*.cor",
                section="load_data",
            ),
            ParamMeta(
                key="mintpy.load.demFile",
                zh_name="DEM文件",
                zh_desc="数字高程模型文件路径",
                type="path",
                path_type="file",
                pattern="*.rdr;*.tif;*.dem",
                section="load_data",
            ),
            ParamMeta(
                key="mintpy.load.lookupYFile",
                zh_name="Y查找表",
                zh_desc="距离-多普勒查找表Y分量",
                type="path",
                path_type="file",
                section="load_data",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.load.lookupXFile",
                zh_name="X查找表",
                zh_desc="距离-多普勒查找表X分量",
                type="path",
                path_type="file",
                section="load_data",
                advanced=True,
            ),
        ],
    ),
    # ==================== 网络修改 ====================
    ParamGroup(
        group_id="network",
        zh_name="网络修改",
        zh_desc="干涉图网络筛选与优化",
        section_order=3,
        default_expanded=True,
        params=[
            ParamMeta(
                key="mintpy.network.tempBaseMax",
                zh_name="最大时间基线",
                zh_desc="最大时间基线（天），留空表示不限制",
                type="int",
                default="no",
                auto_value="no",
                unit="天",
                min_val=1,
                max_val=3650,
                section="modify_network",
            ),
            ParamMeta(
                key="mintpy.network.perpBaseMax",
                zh_name="最大空间基线",
                zh_desc="最大垂直基线（米），留空表示不限制",
                type="int",
                default="no",
                auto_value="no",
                unit="m",
                min_val=1,
                max_val=10000,
                section="modify_network",
            ),
            ParamMeta(
                key="mintpy.network.connNumMax",
                zh_name="最大连接数",
                zh_desc="每个影像最大干涉图连接数，留空表示不限制",
                type="int",
                default="no",
                auto_value="no",
                min_val=1,
                max_val=100,
                section="modify_network",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.network.referenceFile",
                zh_name="参考网络文件",
                zh_desc="指定干涉图网络文件",
                type="path",
                path_type="file",
                section="modify_network",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.network.coherenceBased",
                zh_name="相干性筛选",
                zh_desc="启用基于相干性的网络筛选",
                type="yes_no_auto",
                default="no",
                auto_value="no",
                section="modify_network",
            ),
            ParamMeta(
                key="mintpy.network.minCoherence",
                zh_name="最小相干性",
                zh_desc="平均相干性阈值，低于此值的干涉图被排除",
                type="float",
                default="0.7",
                auto_value="0.7",
                min_val=0.0,
                max_val=1.0,
                section="modify_network",
            ),
            ParamMeta(
                key="mintpy.network.areaRatioBased",
                zh_name="面积比筛选",
                zh_desc="启用基于有效相干面积比的筛选",
                type="yes_no_auto",
                default="no",
                auto_value="no",
                section="modify_network",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.network.minAreaRatio",
                zh_name="最小面积比",
                zh_desc="最小有效相干面积比阈值",
                type="float",
                default="0.75",
                auto_value="0.75",
                min_val=0.0,
                max_val=1.0,
                section="modify_network",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.network.startDate",
                zh_name="开始日期",
                zh_desc="网络筛选的开始日期（YYYYMMDD），留空表示不限制",
                type="date_list",
                default="no",
                auto_value="no",
                section="modify_network",
            ),
            ParamMeta(
                key="mintpy.network.endDate",
                zh_name="结束日期",
                zh_desc="网络筛选的结束日期（YYYYMMDD），留空表示不限制",
                type="date_list",
                default="no",
                auto_value="no",
                section="modify_network",
            ),
            ParamMeta(
                key="mintpy.network.excludeDate",
                zh_name="排除日期",
                zh_desc="排除的影像日期列表（逗号分隔），留空表示不排除",
                type="date_list",
                default="no",
                auto_value="no",
                section="modify_network",
            ),
        ],
    ),
    # ==================== 参考点 ====================
    ParamGroup(
        group_id="reference",
        zh_name="参考点",
        zh_desc="空间参考点配置",
        section_order=4,
        default_expanded=True,
        params=[
            ParamMeta(
                key="mintpy.reference.yx",
                zh_name="像素坐标",
                zh_desc="参考点像素坐标 [y, x]，auto 自动选择高相干点",
                type="text",
                default="auto",
                allow_auto=True,
                section="reference_point",
            ),
            ParamMeta(
                key="mintpy.reference.lalo",
                zh_name="经纬度坐标",
                zh_desc="参考点经纬度 [lat, lon]，auto 自动选择",
                type="text",
                default="auto",
                allow_auto=True,
                section="reference_point",
            ),
            ParamMeta(
                key="mintpy.reference.maskFile",
                zh_name="掩膜文件",
                zh_desc="参考点选择时使用的掩膜文件",
                type="path",
                path_type="file",
                section="reference_point",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.reference.minCoherence",
                zh_name="最小相干性",
                zh_desc="auto 模式下参考点选择的最小相干性阈值",
                type="float",
                default="0.85",
                auto_value="0.85",
                min_val=0.0,
                max_val=1.0,
                section="reference_point",
            ),
        ],
    ),
    # ==================== 解缠误差校正 ====================
    ParamGroup(
        group_id="unwrap",
        zh_name="解缠误差校正",
        zh_desc="相位解缠误差校正方法与参数",
        section_order=5,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.unwrapError.method",
                zh_name="校正方法",
                zh_desc="解缠误差校正方法",
                type="enum",
                default="no",
                auto_value="no",
                valid_values=["bridging", "phase_closure", "bridging+phase_closure", "no"],
                section="correct_unwrap_error",
            ),
            ParamMeta(
                key="mintpy.unwrapError.waterMaskFile",
                zh_name="水体掩膜",
                zh_desc="水体区域掩膜文件",
                type="path",
                path_type="file",
                section="correct_unwrap_error",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.unwrapError.connCompMinArea",
                zh_name="最小连通面积",
                zh_desc="最小连通分量面积阈值（像素数）",
                type="float",
                default="2.5e3",
                auto_value="2.5e3",
                min_val=0,
                max_val=1e6,
                section="correct_unwrap_error",
                advanced=True,
            ),
        ],
    ),
    # ==================== 网络反演 ====================
    ParamGroup(
        group_id="invert",
        zh_name="网络反演",
        zh_desc="时间序列反演参数",
        section_order=6,
        default_expanded=True,
        params=[
            ParamMeta(
                key="mintpy.networkInversion.weightFunc",
                zh_name="权重函数",
                zh_desc="反演权重函数类型，var 推荐用于高相干数据",
                type="enum",
                default="var",
                auto_value="var",
                valid_values=["var", "fim", "coh", "no"],
                section="invert_network",
            ),
            ParamMeta(
                key="mintpy.networkInversion.minNormVelocity",
                zh_name="最小范数速率",
                zh_desc="使用最小范数速度约束",
                type="yes_no_auto",
                default="yes",
                auto_value="yes",
                section="invert_network",
            ),
            ParamMeta(
                key="mintpy.networkInversion.minTempCoh",
                zh_name="最小时间相干性",
                zh_desc="时间相干性阈值，用于生成可靠像素掩膜",
                type="float",
                default="0.7",
                auto_value="0.7",
                min_val=0.0,
                max_val=1.0,
                section="invert_network",
            ),
            ParamMeta(
                key="mintpy.networkInversion.minNumPixel",
                zh_name="最小像素数",
                zh_desc="最小有效像素数阈值",
                type="int",
                default="100",
                auto_value="100",
                min_val=1,
                max_val=1e6,
                section="invert_network",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.networkInversion.maskDataset",
                zh_name="掩膜数据集",
                zh_desc="用于生成掩膜的数据集",
                type="text",
                default="no",
                auto_value="no",
                section="invert_network",
                advanced=True,
            ),
        ],
    ),
    # ==================== SET校正 ====================
    ParamGroup(
        group_id="set",
        zh_name="固体潮校正",
        zh_desc="固体地球潮汐校正",
        section_order=7,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.solidEarthTides",
                zh_name="启用SET校正",
                zh_desc="应用固体地球潮汐校正",
                type="yes_no_auto",
                default="no",
                auto_value="no",
                section="correct_SET",
            ),
        ],
    ),
    # ==================== 电离层校正 ====================
    ParamGroup(
        group_id="ionosphere",
        zh_name="电离层校正",
        zh_desc="电离层延迟校正方法与参数",
        section_order=8,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.ionosphericDelay.method",
                zh_name="校正方法",
                zh_desc="电离层延迟校正方法",
                type="enum",
                default="no",
                auto_value="no",
                valid_values=["split_spectrum", "no"],
                section="correct_ionosphere",
            ),
            ParamMeta(
                key="mintpy.ionosphericDelay.excludeDate",
                zh_name="排除日期",
                zh_desc="电离层校正时排除的影像日期，留空表示不排除",
                type="date_list",
                default="no",
                auto_value="no",
                section="correct_ionosphere",
                advanced=True,
            ),
        ],
    ),
    # ==================== 对流层校正 ====================
    ParamGroup(
        group_id="troposphere",
        zh_name="对流层校正",
        zh_desc="大气延迟校正方法与参数",
        section_order=9,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.troposphericDelay.method",
                zh_name="校正方法",
                zh_desc="对流层延迟校正方法，pyaps 推荐使用ERA5气象数据",
                type="enum",
                default="pyaps",
                auto_value="pyaps",
                valid_values=["pyaps", "height_correlation", "gacos", "no"],
                section="correct_troposphere",
            ),
            ParamMeta(
                key="mintpy.troposphericDelay.weatherModel",
                zh_name="气象模型",
                zh_desc="全球大气模型类型（pyaps方法）",
                type="enum",
                default="ERA5",
                auto_value="ERA5",
                valid_values=["ERA5", "MERRA", "NARR", "ERA5T", "HRES"],
                section="correct_troposphere",
            ),
            ParamMeta(
                key="mintpy.troposphericDelay.weatherDir",
                zh_name="气象数据目录",
                zh_desc="气象模型数据存储目录",
                type="path",
                path_type="dir",
                section="correct_troposphere",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.troposphericDelay.polyOrder",
                zh_name="多项式阶数",
                zh_desc="高度相关方法的多项式阶数",
                type="int",
                default="1",
                auto_value="1",
                min_val=0,
                max_val=5,
                section="correct_troposphere",
                advanced=True,
            ),
        ],
    ),
    # ==================== 去斜 ====================
    ParamGroup(
        group_id="deramp",
        zh_name="相位去斜",
        zh_desc="系统性相位趋势去除",
        section_order=10,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.deramp",
                zh_name="去斜方法",
                zh_desc="相位去斜方法",
                type="enum",
                default="no",
                auto_value="no",
                valid_values=["linear", "quadratic", "no"],
                section="deramp",
            ),
            ParamMeta(
                key="mintpy.deramp.maskFile",
                zh_name="掩膜文件",
                zh_desc="去斜计算时使用的掩膜文件",
                type="path",
                path_type="file",
                section="deramp",
                advanced=True,
            ),
        ],
    ),
    # ==================== 地形校正 ====================
    ParamGroup(
        group_id="topography",
        zh_name="地形校正",
        zh_desc="地形残差校正（DEM误差）",
        section_order=11,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.topographicResidual",
                zh_name="启用地形校正",
                zh_desc="应用地形残差校正",
                type="yes_no_auto",
                default="yes",
                auto_value="yes",
                section="correct_topography",
            ),
            ParamMeta(
                key="mintpy.topographicResidual.polyOrder",
                zh_name="多项式阶数",
                zh_desc="地形残差拟合多项式阶数",
                type="int",
                default="2",
                auto_value="2",
                min_val=0,
                max_val=5,
                section="correct_topography",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.topographicResidual.pixelwiseGeometry",
                zh_name="像素级几何",
                zh_desc="使用像素级几何参数",
                type="yes_no_auto",
                default="yes",
                auto_value="yes",
                section="correct_topography",
                advanced=True,
            ),
        ],
    ),
    # ==================== 残差RMS ====================
    ParamGroup(
        group_id="rms",
        zh_name="残差分析",
        zh_desc="残差均方根分析参数",
        section_order=12,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.residual_RMS.maskFile",
                zh_name="掩膜文件",
                zh_desc="RMS计算使用的掩膜文件",
                type="path",
                path_type="file",
                section="residual_RMS",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.residual_RMS.deramp",
                zh_name="去斜方法",
                zh_desc="RMS计算时的去斜方法",
                type="enum",
                default="quadratic",
                auto_value="quadratic",
                valid_values=["linear", "quadratic", "no"],
                section="residual_RMS",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.residual_RMS.cutoff",
                zh_name="截断值",
                zh_desc="残差RMS截断值（米）",
                type="float",
                default="3",
                auto_value="3",
                min_val=0,
                max_val=100,
                unit="m",
                section="residual_RMS",
                advanced=True,
            ),
        ],
    ),
    # ==================== 参考日期 ====================
    ParamGroup(
        group_id="ref_date",
        zh_name="参考日期",
        zh_desc="时间序列参考日期设置",
        section_order=13,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.reference.date",
                zh_name="参考日期",
                zh_desc="时间序列的参考日期（YYYYMMDD），默认从 reference_date.txt 读取",
                type="date_list",
                default="reference_date.txt",
                auto_value="reference_date.txt",
                section="reference_date",
            ),
        ],
    ),
    # ==================== 速率估计 ====================
    ParamGroup(
        group_id="velocity",
        zh_name="速率估计",
        zh_desc="形变速率时间函数拟合",
        section_order=14,
        default_expanded=True,
        params=[
            ParamMeta(
                key="mintpy.timeFunc.startDate",
                zh_name="开始日期",
                zh_desc="速率估计的开始日期，留空表示不限制",
                type="date_list",
                default="no",
                auto_value="no",
                section="velocity",
            ),
            ParamMeta(
                key="mintpy.timeFunc.endDate",
                zh_name="结束日期",
                zh_desc="速率估计的结束日期，留空表示不限制",
                type="date_list",
                default="no",
                auto_value="no",
                section="velocity",
            ),
            ParamMeta(
                key="mintpy.timeFunc.excludeDate",
                zh_name="排除日期",
                zh_desc="速率估计时排除的日期，默认从 exclude_date.txt 读取",
                type="date_list",
                default="exclude_date.txt",
                auto_value="exclude_date.txt",
                section="velocity",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.timeFunc.polynomial",
                zh_name="多项式阶数",
                zh_desc="时间函数多项式阶数，1 = 线性速率",
                type="int",
                default="1",
                auto_value="1",
                min_val=0,
                max_val=5,
                section="velocity",
            ),
            ParamMeta(
                key="mintpy.timeFunc.periodic",
                zh_name="周期函数",
                zh_desc="周期性成分周期（年），1 = 年周期，0.5 = 半年周期，留空表示无",
                type="text",
                default="no",
                auto_value="no",
                section="velocity",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.timeFunc.stepDate",
                zh_name="阶跃日期",
                zh_desc="形变阶跃事件日期（YYYYMMDD），留空表示无",
                type="date_list",
                default="no",
                auto_value="no",
                section="velocity",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.timeFunc.uncertaintyQuantification",
                zh_name="不确定性量化",
                zh_desc="速率不确定性量化方法",
                type="enum",
                default="residue",
                auto_value="residue",
                valid_values=["residue", "covariance", "bootstrap"],
                section="velocity",
                advanced=True,
            ),
        ],
    ),
    # ==================== 地理编码 ====================
    ParamGroup(
        group_id="geocode",
        zh_name="地理编码",
        zh_desc="坐标转换与输出分辨率设置",
        section_order=15,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.geocode",
                zh_name="启用地理编码",
                zh_desc="将结果转换到地理坐标系",
                type="yes_no_auto",
                default="yes",
                auto_value="yes",
                section="geocode",
            ),
            ParamMeta(
                key="mintpy.geocode.SNWE",
                zh_name="输出范围",
                zh_desc="输出范围 [S, N, W, E]（度），留空使用全部范围",
                type="bbox",
                default="none",
                auto_value="none",
                section="geocode",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.geocode.laloStep",
                zh_name="输出分辨率",
                zh_desc="地理编码输出分辨率（度）",
                type="float",
                default="none",
                auto_value="none",
                min_val=1e-5,
                max_val=1.0,
                unit="度",
                section="geocode",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.geocode.interpMethod",
                zh_name="插值方法",
                zh_desc="地理编码插值方法",
                type="enum",
                default="nearest",
                auto_value="nearest",
                valid_values=["nearest", "linear", "cubic"],
                section="geocode",
                advanced=True,
            ),
        ],
    ),
    # ==================== 输出控制 ====================
    ParamGroup(
        group_id="output",
        zh_name="输出控制",
        zh_desc="结果输出与可视化选项",
        section_order=16,
        default_expanded=False,
        collapsible=True,
        params=[
            ParamMeta(
                key="mintpy.save.kmz",
                zh_name="Google Earth KMZ",
                zh_desc="保存地理编码结果为Google Earth KMZ文件",
                type="yes_no_auto",
                default="yes",
                auto_value="yes",
                section="geocode",
            ),
            ParamMeta(
                key="mintpy.save.hdfEos5",
                zh_name="HDF-EOS5格式",
                zh_desc="保存为HDF-EOS5格式",
                type="yes_no_auto",
                default="no",
                auto_value="no",
                section="geocode",
                advanced=True,
            ),
            ParamMeta(
                key="mintpy.plot",
                zh_name="生成图表",
                zh_desc="自动生成结果可视化图表",
                type="yes_no_auto",
                default="yes",
                auto_value="yes",
                section="geocode",
            ),
        ],
    ),
]


def get_params_for_step(step_id: str) -> List[ParamMeta]:
    """根据处理步骤ID返回相关参数列表"""
    group_ids = STEP_TO_GROUPS.get(step_id, [])
    params = []
    for group in PARAM_GROUPS:
        if group.group_id in group_ids:
            params.extend(group.params)
    return params


def get_group_for_step(step_id: str) -> List[ParamGroup]:
    """根据处理步骤ID返回相关参数分组"""
    group_ids = STEP_TO_GROUPS.get(step_id, [])
    return [g for g in PARAM_GROUPS if g.group_id in group_ids]


def get_core_groups() -> List[ParamGroup]:
    """获取核心参数分组（默认展开的）"""
    return [g for g in PARAM_GROUPS if g.default_expanded]


def get_all_param_keys() -> List[str]:
    """获取所有参数键名列表"""
    keys = []
    for group in PARAM_GROUPS:
        for param in group.params:
            keys.append(param.key)
    return keys
