# Sentinel-1 Subswath Detector

## 功能说明

根据任务区范围（shapefile格式）判断Sentinel-1 IW模式数据需要处理哪些subswath。

Sentinel-1 IW模式数据包含3个subswath（IW1, IW2, IW3），每个subswath覆盖不同的空间范围。在处理InSAR数据前，通过判断任务区与各subswath的覆盖范围是否相交，可以确定需要处理哪些subswath，从而节省计算资源。

## 使用方法

### 命令行使用

```bash
python subswath_detector.py <sentinel1_zip_path> <shapefile_path>
```

示例：
```bash
python subswath_detector.py data/raw/S1A_IW_SLC.zip data/raw/target.shp
```

### Python API使用

```python
from subswath_detector import detect_subswaths

# 检测需要的subswath
subswaths = detect_subswaths(
    'data/raw/S1A_IW_SLC.zip',
    'data/raw/target.shp'
)

print(f"需要处理的subswath: {subswaths}")
# 输出: [1, 2] 或 [1] 或 []
```

### 类方式使用

```python
from subswath_detector import SubswathDetector

detector = SubswathDetector(
    sentinel1_zip_path='data/raw/S1A_IW_SLC.zip',
    shapefile_path='data/raw/target.shp'
)

subswaths = detector.detect_subswaths()
print(f"需要处理的subswath: {subswaths}")
```

## 输入参数

- `sentinel1_zip_path`: Sentinel-1数据zip文件路径（SAFE格式压缩包）
- `shapefile_path`: 任务区shapefile文件路径（.shp文件）

## 输出

返回一个整数列表，表示需要处理的subswath编号：
- `[1, 2]`: 需要处理subswath 1和2
- `[1]`: 只需要处理subswath 1
- `[]`: 没有subswath与任务区相交

## 工作原理

1. **提取任务区范围**: 从shapefile中读取所有多边形，计算并集，获取边界框（bounding box）
2. **提取subswath覆盖范围**: 从Sentinel-1 SAFE数据的annotation XML文件中提取每个subswath的geolocationGrid坐标，计算覆盖范围的边界框
3. **空间交集判断**: 检查每个subswath的边界框是否与任务区边界框相交
4. **返回结果**: 返回所有与任务区相交的subswath编号列表

## 依赖安装

```bash
pip install -r requirements.txt
```

或直接安装：
```bash
pip install geopandas shapely
```

## 异常处理

脚本包含详细的异常处理，会在以下情况抛出异常：
- 文件不存在
- 文件格式错误（无效的zip文件或shapefile）
- 无法解析Sentinel-1数据
- shapefile为空

所有异常信息都会详细说明错误原因和位置。

## 测试

运行测试脚本：
```bash
python test_subswath_detector.py
```

## 注意事项

1. Sentinel-1数据必须是IW模式的SLC产品
2. Shapefile必须包含有效的几何数据
3. 脚本会自动处理shapefile中的多个多边形，计算它们的并集范围
4. 脚本从annotation XML文件的geolocationGrid中提取坐标信息
