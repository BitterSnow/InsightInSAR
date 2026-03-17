# Subswath [1] 实际处理结果报告

## ✅ 处理状态：成功完成

**处理时间**: 2026-02-20 18:03:35  
**Subswath**: [1]  
**处理范围**: target.shp 定义的区域（SNWE: [31.728959, 32.199081, 101.781392, 102.099612]）

---

## 📁 生成的数据文件

### 容器内路径（Docker 内部）
```
/app/data/radar/slc_out/S1A_IW_SLC__1SDV_20180102T110854_20180102T110922_019975_022063_79FC/IW1/
```

### 宿主机路径（Windows）
```
D:\coding\insar-system\data\radar\slc_out\S1A_IW_SLC__1SDV_20180102T110854_20180102T110922_019975_022063_79FC\IW1\
```

---

## 📄 生成的文件列表

| 文件名 | 大小 | 类型 | 说明 |
|--------|------|------|------|
| `burst_01.slc.vrt` | 808 bytes | VRT | Burst 1 虚拟栅格文件 |
| `burst_01.slc.xml` | 3,959 bytes | XML | Burst 1 元数据 |
| `burst_02.slc.vrt` | 808 bytes | VRT | Burst 2 虚拟栅格文件 |
| `burst_02.slc.xml` | 3,959 bytes | XML | Burst 2 元数据 |
| `burst_03.slc.vrt` | 808 bytes | VRT | Burst 3 虚拟栅格文件 |
| `burst_03.slc.xml` | 3,959 bytes | XML | Burst 3 元数据 |
| `burst_04.slc.vrt` | 809 bytes | VRT | Burst 4 虚拟栅格文件 |
| `burst_04.slc.xml` | 3,959 bytes | XML | Burst 4 元数据 |
| `burst_05.slc.vrt` | 809 bytes | VRT | Burst 5 虚拟栅格文件 |
| `burst_05.slc.xml` | 3,959 bytes | XML | Burst 5 元数据 |

**总计**: 5 个 SLC VRT 文件 + 5 个 XML 元数据文件

---

## 🔄 路径映射说明

根据 `docker-compose.yml` 配置：
```yaml
volumes:
  - ./data:/app/data
```

**映射规则**:
- 容器内: `/app/data/...` 
- 宿主机: `D:\coding\insar-system\data\...`

**示例转换**:
- 容器: `/app/data/radar/slc_out/.../IW1/burst_01.slc.vrt`
- 宿主机: `D:\coding\insar-system\data\radar\slc_out\...\IW1\burst_01.slc.vrt`

---

## ✅ 验证结果

### 1. 容器内文件存在性 ✅
```bash
docker compose exec worker ls -lh /app/data/radar/slc_out/.../IW1/
```
**结果**: 所有文件已成功生成

### 2. 宿主机文件存在性 ✅
```powershell
Test-Path "data\radar\slc_out\...\IW1"
```
**结果**: `True` - 文件已自动映射到宿主机

### 3. 文件时间戳 ✅
所有文件的时间戳均为 `2026/2/20 18:03:35`，与处理完成时间一致。

---

## 📊 处理统计

- **输入数据**: `S1A_IW_SLC__1SDV_20180102T110854_20180102T110922_019975_022063_79FC.zip`
- **检测到的 Subswath**: [1]（与 target.shp 相交）
- **处理的 Burst 数量**: 5 个（从原始 9 个裁剪到 5 个）
- **输出格式**: VRT（虚拟栅格）+ XML（元数据）
- **处理模式**: Virtual SLC（不生成实际 SLC 文件，仅生成索引）

---

## 🎯 结论

✅ **Subswath [1] 处理成功完成**

✅ **所有生成的数据文件已自动映射到宿主机路径**

✅ **文件可直接在 Windows 文件系统中访问**:
```
D:\coding\insar-system\data\radar\slc_out\S1A_IW_SLC__1SDV_20180102T110854_20180102T110922_019975_022063_79FC\IW1\
```

---

## 📝 注意事项

1. **VRT 文件**: 这些是虚拟栅格文件，指向 ZIP 内的实际 TIFF 数据。使用 GDAL 工具（如 `gdalinfo`）可以查看和读取。
2. **数据持久化**: 由于使用了 Docker volume 映射，所有数据在容器重启后仍然保留在宿主机。
3. **后续处理**: 这些 SLC VRT 文件可用于后续的干涉处理（interferometry）步骤。

---

## 🔍 快速访问命令

### 查看容器内文件
```bash
docker compose exec worker ls -lh /app/data/radar/slc_out/S1A_IW_SLC__1SDV_20180102T110854_20180102T110922_019975_022063_79FC/IW1/
```

### 查看宿主机文件
```powershell
Get-ChildItem "D:\coding\insar-system\data\radar\slc_out\S1A_IW_SLC__1SDV_20180102T110854_20180102T110922_019975_022063_79FC\IW1"
```

### 验证 VRT 文件内容
```bash
docker compose exec worker gdalinfo /app/data/radar/slc_out/.../IW1/burst_01.slc.vrt
```
