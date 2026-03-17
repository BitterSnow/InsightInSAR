# 路径映射和相对路径验证报告

## ✅ 修改完成

### 1. 输出目录结构调整

**修改前**:
- 输出目录: `/app/data/radar/slc_out/S1A_IW_SLC__.../IW1/`

**修改后**:
- 输出目录: `/app/data/radar/processing/s1_import/S1A_IW_SLC__.../IW1/`
- 宿主机映射: `D:\coding\insar-system\data\radar\processing\s1_import\S1A_IW_SLC__...\IW1\`

### 2. VRT 文件相对路径修复

**修复前** (ISCE2 生成的绝对路径):
```xml
<SourceFilename relativeToVRT="1">/vsizip//app/data/radar/S1A_IW_SLC__...zip/SAFE/measurement/xxx.tiff</SourceFilename>
```

**修复后** (相对路径):
```xml
<SourceFilename relativeToVRT="1">/vsizip/../../../../S1A_IW_SLC__...zip/SAFE/measurement/xxx.tiff</SourceFilename>
```

### 3. 路径结构说明

```
/app/data/radar/
├── S1A_IW_SLC__...zip                    (ZIP 文件)
└── processing/
    └── s1_import/
        └── S1A_IW_SLC__.../
            └── IW1/
                ├── burst_01.slc.vrt      (VRT 文件，使用相对路径指向 ZIP)
                ├── burst_01.slc.xml
                └── ...
```

**相对路径计算**:
- VRT 文件位置: `processing/s1_import/xxx/IW1/burst_01.slc.vrt`
- ZIP 文件位置: `S1A_IW_SLC__...zip` (在 `radar/` 目录下)
- 相对路径: `../../../../S1A_IW_SLC__...zip` (向上 4 级到 `radar/` 目录)

---

## ✅ 验证结果

### 1. 文件生成验证 ✅
- ✅ 所有 VRT 文件已成功生成在 `processing/s1_import/` 目录下
- ✅ 文件已自动映射到宿主机 `D:\coding\insar-system\data\radar\processing\...`

### 2. 相对路径验证 ✅
- ✅ VRT 文件中的 `<SourceFilename relativeToVRT="1">` 已正确设置为相对路径
- ✅ 路径格式: `/vsizip/../../../../xxx.zip/SAFE/measurement/xxx.tiff`
- ✅ 相对路径从 VRT 文件位置正确指向 ZIP 文件位置

### 3. 路径映射验证 ✅
- ✅ 容器内路径: `/app/data/radar/processing/s1_import/...`
- ✅ 宿主机路径: `D:\coding\insar-system\data\radar\processing\s1_import\...`
- ✅ Docker volume 映射 (`./data:/app/data`) 正常工作

---

## 📝 代码修改位置

### `backend/services/s1_processing_service.py`

1. **输出目录修改** (第 215-218 行):
```python
# 修改前
out_dir = os.path.join(os.path.dirname(request.zip_path), "slc_out", base)

# 修改后
radar_dir = os.path.dirname(request.zip_path)  # /app/data/radar
out_dir = os.path.join(radar_dir, "processing", "s1_import", base)
```

2. **新增相对路径修复函数** (第 78-146 行):
```python
def fix_vrt_relative_path(vrt_path: str, zip_path: str) -> None:
    """修复 VRT 文件中的相对路径，确保 relativeToVRT="1" 的路径能够正确指向 ZIP 文件"""
    # ... 实现细节 ...
```

3. **调用相对路径修复** (第 195-199 行):
```python
if name.endswith(".vrt") or name.endswith(".slc.vrt"):
    vrt_path = os.path.join(swath_out, name)
    # 修复 VRT 文件中的相对路径，确保指向 ZIP 文件的路径正确
    fix_vrt_relative_path(vrt_path, zip_path)
    slc_vrt_paths.append(vrt_path)
```

---

## 🎯 后续处理兼容性

### GDAL 相对路径解析

当 `relativeToVRT="1"` 时，GDAL 会将路径解析为相对于 VRT 文件的位置：

1. **VRT 文件位置**: `/app/data/radar/processing/s1_import/xxx/IW1/burst_01.slc.vrt`
2. **相对路径**: `/vsizip/../../../../S1A_IW_SLC__...zip/...`
3. **解析结果**: `/vsizip//app/data/radar/S1A_IW_SLC__...zip/...`

这样，后续的 ISCE2 处理步骤（如干涉处理、配准等）可以正确读取 VRT 文件并访问 ZIP 内的数据。

---

## ✅ 结论

1. ✅ **中间数据存储位置**: 已修改为 `processing/` 子目录结构，不增加容器体积
2. ✅ **相对路径修复**: VRT 文件中的路径已正确设置为相对路径，满足后续处理要求
3. ✅ **路径映射**: 所有数据文件已正确映射到宿主机，可通过 Windows 文件系统直接访问

所有修改已完成并验证通过！
