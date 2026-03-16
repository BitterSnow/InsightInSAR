# geom_reference 栅格数值异常 — 根因定位与修复建议

## 1. 现象
- 使用 **topsStack topo**（`contrib/stack/topsStack/topo.py`）在 Windows 上生成 `geom_reference/IW1/hgt_01.rdr` 等文件。
- QGIS 打开 hgt/lat/lon 等 VRT 时值域异常（约 1e80 量级），不像高程/经纬度。
- 字节序诊断结论：**LSB 与 MSB 解释均不像合理高程**，DEM 本身为 LSB 且数值正常（779–4669 m）。

## 2. 数据流（谁在写 hgt_01.rdr）
1. **topsStack/topo.py**  
   - 对每个 burst 调用 `call_topo(dirname, demImage, reference, ind)`。  
   - 设置 `topo.heightFilename = .../IW1/hgt_01.rdr`，然后 `topo.topo()`。
2. **zerodop/topozero/Topozero.py**  
   - `createImages()` 里对 height 只做：  
     `self.heightImage.initImage(self.heightFilename, 'write', width, 'DOUBLE')`，**未** `setLength(self.length)`。  
   - 随后 `self.heightImage.createImage()` → 触发 DataAccessor 创建/打开文件。  
   - `getImagePointer()` 把 C++ accessor 句柄传给 Fortran。
3. **Fortran topozero**  
   - 每行计算高度 `z`，调用 `setLineSequential_r8(heightAccessor, z)`。  
   - C++ 侧 `DataAccessor::setLineSequential` → `InterleavedAccessor::setStream` 按行写入文件。

## 3. 已排除
- **VRT/XML 路径**：DEM XML 已改为本地路径，问题依旧。  
- **输出字节序**：LSB/MSB 解释都异常，非“VRT 标 LSB 实际写 MSB”。  
- **DEM 字节序**：DEM 为 LSB，数值在合理高程范围。  
- **文件类型/大小**：hgt_01.rdr 为约 257 MB 的原始 Float64 栅格，尺寸正确。

## 4. 可能根因（按优先级）
0. **Windows 下 fstream 未使用二进制模式（已修复）**  
   - 在 Windows 上，`std::fstream` 默认以**文本模式**打开；会将来字节 0x0a 写成 0x0d 0x0a，从而破坏 float/double 的二进制表示，导致读出约 ±1e308 等异常值。  
   - **修复**：在 `InterleavedAccessor::openFile()` 中所有 `fd.open(...)` 增加 `ios_base::binary`（见 `lib/isce2-main/components/iscesys/ImageApi/InterleavedAccessor/src/InterleavedAccessor.cpp`）。  
   - **生效条件**：需**重新编译 ISCE2**（含 iscesys/ImageApi 及依赖它的 topozero 等），并重跑 Step 1 后再做诊断。

1. **输出 Image 未设 length、未调用 createFile**  
   - Topozero 只对 lat/lon/height 等做 `initImage(..., width, ...)`，**从未** `image.setLength(self.length)`。  
   - `Image.createImage()` 依赖“文件已存在且大小 = width×length×size×bands”；对新建写文件，若 length 未设，会按 0 处理，与 0 字节文件“一致”，检查通过。  
   - 文件实际由 Fortran 逐行写大，大小虽对，但若 C++ 端对“未预分配文件”或 LineCounter 有平台差异，**有可能**导致写错位或未正确刷新。  
   - **建议**：在 `createImages()` 里对 lat/lon/height（及 los/inc/mask）在 `createImage()` 前执行 `image.setLength(self.length)`，并在 C++ 支持的前提下在打开写文件后调用 `createFile(self.length)` 预分配，再让 Fortran 写。

2. **多进程 (multiprocessing)**  
   - topsStack topo 使用 `pool.map(call_topo, inputs)`，每个 burst 在**子进程**中跑。  
   - Windows 上为 **spawn**，子进程重新 import，C++ 扩展与 DataAccessor 在子进程中重新加载。  
   - 若子进程内 accessor 句柄或文件描述符与父进程/其他进程串扰，或 DLL 在 spawn 下行为异常，可能写出错。  
   - **建议**：先用 **`--numProcess 1`** 跑一次 topo，看单进程下 hgt_01.rdr 是否仍异常；若单进程正常，则问题与多进程相关。

3. **Fortran 计算或传参**  
   - 若上述均排除，则可能为 Fortran 内高程解算在 Windows 上的数值/输入问题（如轨道时间、OpenMP、或与 Linux 不同的默认行为）。  
   - 需与 **同景、同参数在 Linux 上的 topo 结果** 逐像素对比（同一 burst、同一行/列）才能进一步缩小范围。

## 5. 建议修复（最小改动）
在 **Topozero.createImages()** 中，对用于写的 Image（lat/lon/height/los/inc/mask）在调用 `createImage()` 之前：
- 执行 `image.setLength(self.length)`；  
- 若该 Image 类型在 ISCE 中支持 `createFile(lines)`，则在 `createImage()` 之后、`getImagePointer()` 之前对写模式 Image 调用 `image.createFile(self.length)`（需确认 Image/DataAccessor 接口是否暴露并适用于 BIP 写）。

这样可保证“先按正确 length 预分配文件，再让 Fortran 按行写”，避免依赖“0 字节起、逐行扩展”的未定义行为。

## 6. 涉及文件
- 写入几何产品的入口：`lib/isce2-main/contrib/stack/topsStack/topo.py`  
- Topozero 与 Image 创建：`lib/isce2-main/install/packages/isce/components/zerodop/topozero/Topozero.py`（及 isce2 同名路径）  
- 写接口：`lib/isce2-main/components/iscesys/ImageApi/DataAccessor/`、**`InterleavedAccessor`**（此处 openFile 须用 binary 模式）  
- Fortran 写高度：`lib/isce2-main/components/zerodop/topozero/src/topozero.f90`（`setLineSequential_r8(heightAccessor, z)`）

## 7. 验证步骤
1. 应用上述 **setLength + createFile** 修改后，重跑 Step1（仅 topo），再对 `geom_reference/IW1/hgt_01.rdr` 跑 `scripts/diagnose_topo_byteorder.py`，看 LSB 是否落在合理高程。
2. **桌面验证**：用 `scripts/start_desktop.bat` 启动桌面，在 stack 流程里只跑第一步（run_01）；Step1 由子进程执行且 PYTHONPATH 已含 `install/packages`，会加载修改后的 Topozero，无需单独配环境。
3. 用 **`--numProcess 1`** 跑 topo，对比当前多进程结果。
4. 若有 Linux 同景结果，对同一 burst 的同一像素用 Python 读 rdr 比较数值。

---

## 8. 若 setLength+createFile 后数值仍错（如 QGIS 显示 -179~179 且像素 535/907/998）

说明预分配修复未解决根本原因，需按下面顺序排查。

### 8.1 先确认“当前文件”的原始字节
对**重新处理后的** `hgt_01.rdr` 跑诊断，看 LSB/MSB 是否像高程：

```bash
python scripts/diagnose_topo_byteorder.py --hgt "D:\processing\tianfu\processing\geom_reference\IW1\hgt_01.rdr"
```

- **若 LSB 的 min/max 已在合理高程（如 500–5000）**：磁盘上的数据可能已正确，问题更可能是 **QGIS 显示** 或 **VRT 元数据**（ByteOrder/DataType/SourceFilename）。可检查 `geom_reference/IW1/hgt_01.rdr.vrt` 是否指向 `hgt_01.rdr`、是否为 Float64、ByteOrder=LSB，并在 QGIS 中“图层属性 → 符号系统”刷新统计或手动设最小/最大值为 DEM 范围。
- **若 LSB 仍为 1e80 量级或 nan**：说明写入内容仍错，需继续下面步骤。

### 8.2 确认打开的是高程而不是经度
图例 -179~179 很像**经度**。请确认在 QGIS 里加载的是 **hgt_01.rdr.vrt**（高程），不是 **lon_01.vrt**（经度）。若确为 hgt_01 却显示 -179~179，则同一栅格中可能混有经纬度范围的值（例如 lat/lon 与 hgt 写错文件或指针混用）。

### 8.3 强制 topo 单进程
Stack 初始化时会把 `numProcess4topo` 写入 run_01 的 config；SentinelWrapper 跑 topo 时读该 config。若初始化时用了 `-n 2` 等，topo 会多进程。建议：

- **重新做一次 stack 初始化**，显式加上 `--num_proc4topo 1`（以及原先的 `-n 1` 若需要），再只执行 run_01；
- 或在 `configs/config_run_01_*` 里把 `numProcess : 1` 改为确认是 1，然后只重跑 Step 1。

若单进程下 hgt_01 正常，则问题与 Windows 下 topo 多进程（spawn + accessor/DLL）有关。

### 8.4 仍异常时（含 getLine 修正后仍 179/-179）
- **务必用新进程跑 topo**：在**新开**的 PowerShell 中执行 `run_topo_burst1_only.ps1`（不要在用过多年的、已 import isce 的 Python 的终端里跑），否则可能仍加载旧的 `DataAccessor.pyd`，写出的仍是坏数据。
- **先看磁盘上的原始值**：
  ```bash
  python scripts/diagnose_geom_first_values.py "D:\processing\tianfu\processing\geom_reference\IW1"
  python scripts/diagnose_geom_troubleshoot.py "D:\processing\tianfu\processing\geom_reference\IW1"
  ```
  - 若 **LSB 前 4 个值** 中 lat≈31、lon≈101、hgt 为合理高程：说明 **.rdr 文件内容正确**，问题在 **VRT 或 QGIS 解释**。可在 QGIS 中不用 VRT、用「栅格 → 其他 → 栅格」手动添加 `.rdr`，数据类型选 Float64、字节序 LSB；或检查/修正 `hgt_01.rdr.vrt` 中的 ByteOrder/DataType。
  - 若 LSB 前几个值仍是 179/-179 或极大/NaN：说明**写端仍错**，确认已执行 `copy_dataaccessor_to_isce.ps1` 且无进程占用，再在新终端重跑 topo。
- 用 Python 直接读**同一行**的 `hgt_01.rdr`、`lat_01.rdr`、`lon_01.rdr`（例如第 0 行，Float64 LSB），比较数值：若 hgt 文件中出现典型经度（-180~180）或纬度（-90~90），而 lat/lon 文件中出现高程量级，则可能是 **accessor 与文件对应关系** 在 Windows 上错乱（如指针传错）。
- 与 **Linux 同景、同参数** 的 topo 结果做同一 burst、同一行/列的数值对比，区分是“计算错”还是“写入/指针错”。

---

## 9. 修复「Windows 文本模式破坏二进制」后（InterleavedAccessor + binary）

1. **重新编译 ISCE2**（使修改后的 `InterleavedAccessor.cpp` 生效）  
   源码已改：`lib/isce2-main/components/iscesys/ImageApi/InterleavedAccessor/src/InterleavedAccessor.cpp` 中所有 `openFile()` 的 `fd.open(...)` 已加上二进制标志（`kBinary = 0x20`）。  
   - **PATH**：编译前请将 **MSYS2 UCRT64** 放在 PATH 最前（例如与 `tools/configure-build-isce2-miniconda3.ps1` 一致），否则 g++ 可能静默失败。  
   - 在 **MSYS2 UCRT64** 或已配置好 ISCE2 的终端中执行：
   ```bash
   cd /d/coding/insar-system/lib/isce2-main/build
   ninja DataAccessorLib
   ninja DataAccessor
   cmake --install . --prefix ../install
   ```
   若本机 `cmake --build` 在 PowerShell 下执行时 g++ 报错未显示，请在同一台机用 **MSYS2 UCRT64 终端** 进入 `build` 目录后执行 `ninja DataAccessorLib`，查看完整编译错误再修复。

2. **将新 DataAccessor.pyd 同步到 isce 包**  
   `cmake --install` 只会更新 `install/packages/isce2/.../DataAccessor.pyd`，而 topsStack/topo 通过 **`import isce`** 加载的是 **`install/packages/isce/...`**。因此安装后必须把新编译的 `.pyd` 复制到 isce 包下，否则运行时仍会用旧扩展。  
   ```powershell
   .\scripts\copy_dataaccessor_to_isce.ps1
   ```
   若提示目标文件被占用，请先关闭所有使用 isce 的 Python 进程（含可能加载了 isce 的 Cursor/终端），再执行上述脚本。

3. **重跑 Step 1**（桌面或 `python scripts/run_topo_checks.py --run-step1`）。
4. **再跑诊断**：
   ```bash
   python scripts/diagnose_topo_byteorder.py --hgt "D:\processing\tianfu\processing\geom_reference\IW1\hgt_01.rdr"
   python scripts/diagnose_geom_one_line.py "D:\processing\tianfu\processing\geom_reference\IW1"
   ```
   若 LSB 落在合理高程、hgt/lat/lon 第一行均 [合理]，则问题已解决。

---

## 10. topo 卡在「API open (R): ... isce2_gdal_*.bsq」且 CPU/磁盘几乎为 0

**现象**：Step 1 运行到 topo 时，最后一行输出为 `API open (R): C:\...\Temp\isce2_gdal_xxxxx.bsq`，之后长时间无输出；任务管理器中对应 Python/PowerShell 的 CPU、磁盘、网络均接近 0（进程像挂起而非在算）。

**原因**：该输出来自 C++ InterleavedAccessor 打开**只读**临时 BSQ 文件（多为 DEM 或参考栅格经 GDAL 转成临时 BSQ 后由 C++ 打开）。卡住通常不是算力不足，而是**阻塞**，可能包括：

1. **杀毒/安全软件**：对 `%TEMP%` 或新生成的 `.bsq` 做实时扫描或锁定，导致 C++ 的 `fd.open()` 或后续读操作长时间等待。
2. **磁盘/文件系统**：临时目录在慢盘、网络盘或休眠盘上，或文件被其他进程占用。
3. **Windows 上 C++ fstream 或 GDAL 行为**：在个别环境下打开/读大文件时出现阻塞（较少见）。

**建议操作**（按顺序尝试）：

1. **结束当前卡住的进程**  
   在运行 Step 1 的 PowerShell 窗口按 `Ctrl+C`，或在任务管理器中结束对应「Python」及「Windows PowerShell」进程。

2. **排除临时目录的实时扫描**  
   - 在 Windows 安全中心 / 杀毒软件中，为「实时保护」或「按需扫描」添加排除项：  
     `C:\Users\<你的用户名>\AppData\Local\Temp`  
   - 或将 ISCE2 工作目录、`D:\processing` 等数据目录加入排除列表后再重跑 Step 1。

3. **确认 Temp 所在盘与权限**  
   - 在 PowerShell 中执行：`[System.IO.Path]::GetTempPath()` 查看临时目录。  
   - 确认该目录在本地盘且无「只读」等异常；若在 OneDrive 或网络盘，可设置环境变量 `TEMP`/`TMP` 指向本地盘（如 `D:\Temp`）后重试。

4. **若仍卡在同一位置（已排除杀毒、已用本地盘 Temp）**  
   - **定位卡点**：源码中已在 `InterleavedAccessor::openFile()` 的 `fd.open()` 后增加调试输出 `API open (R) done: ...`。重新编译并安装后重跑 Step 1：  
     - 若**从未**出现 `API open (R) done`，则卡在 **C++ 的 fd.open()**。  
     - 若**出现** `API open (R) done` 后无新输出（已确认），则卡在 **open 之后的首次读或 Fortran 计算**。  
   - **进一步区分**：运行 `.\scripts\run_step1_with_accessor_debug.ps1`（内部设置 `ISCE_DEBUG_ACCESSOR=1`），会多打印 `API getStream start numEl=...` / `API getStream end numEl=...`。  
     - 若出现 **`API getStream start` 后不再有 `API getStream end`**：卡在 **C++ 的 FileObject.read()**（读该 .bsq 时阻塞）。  
     - 若**从未**出现 `API getStream start`：卡在 **Fortran 或 Python** 在第一次调用 getStream 之前的逻辑（如行循环、初始化等）。  
   - 其他尝试：使用**非 VRT 的 DEM**（如 GeoTIFF）减少 GDAL→临时 BSQ 路径；或与 Linux 同景对比，确认是否仅 Windows 上复现。

### 10.1 卡点精确定位（已确认）

通过 `createImages` 与 Python 调试打印可确认：

- 输出中会出现 **`createImages: before demImage.createImage()`**，随后是 **`API open (R): ...bsq`** 与 **`API open (R) done: ...bsq`**。
- **不会**出现 **`createImages: demImage.createImage() done, before latImage.createImage()`**。

**结论**：进程卡在 **`demImage.createImage()` 内部**，且是在 **C++ 端 `openFile()` 已返回（即 "API open (R) done" 已打印）之后**、`createImage()` 返回 Python 之前。即阻塞发生在「打开只读 .bsq 文件之后」的某段逻辑，可能在：
- C++ InterleavedAccessor 的 `init()` 或 `openFile()` 返回后的后续初始化（如根据文件大小设置 NumberOfLines 等）；
- 或 Python 侧 Image/DataAccessor 在收到 C++ open 完成后的后续调用。

**修复（已实现）**：在 Windows 上，`InterleavedAccessor::init()` 中原先通过 `seekg(0, ios::end)` + `tellg()` 获取只读文件大小，该操作在部分环境下会阻塞。已改为在 **只读 + Windows** 时用 **`_stat64(Filename)`** 取文件大小，不再对已打开的 fstream 做 `seekg(0, end)`，从而避免卡住。  
- 源码：`InterleavedAccessor.cpp` 中 `#if defined(_WIN32) || defined(__MINGW32__)` 且 `accessMode == "read"` 时走 `_stat64` 分支（MinGW 也会走该分支）。  
- 生效：需重新编译 DataAccessorLib/DataAccessor、安装、并执行 `scripts/copy_dataaccessor_to_isce.ps1` 将新 `.pyd` 拷入 `packages/isce`。若复制时提示目标文件被占用，请**先关闭 Cursor、所有 PowerShell 与 Python 进程**，再执行复制脚本；或在新开 cmd 中执行 `scripts\replace_dataaccessor_after_close.bat` 完成替换后重跑 Step 1。

### 10.2 卡死由后续改动引入（先前版本无卡死、仅 geom_reference 异常）

**事实**：在未做 DataAccessor/InterleavedAccessor 修改的“之前版本”中，Step 1 能跑完，仅存在 geom_reference 数值异常；卡死是在后续为修复 geom_reference 所做的改动之后出现的。

**可能原因**：  
1. **只读时使用 binary 打开**：为修复写端二进制破坏而加的 `kBinary` 若用于**读**，在 MinGW/Windows 上可能与 `seekg(0, end)` 或后续逻辑组合导致阻塞。  
2. **MinGW 未定义 _WIN32**：若仅用 `#if defined(_WIN32)`，MinGW 下可能未走 _stat64 分支，仍执行 `seekg(0, ios::end)` 导致卡死。  
3. **rewindAccessor()**：只读时内部调用 `seekg(0, ios::end)`，若在 createImage 或首次读前后被调用，也会在 Windows 上阻塞。

**本次调整**：  
- **读模式不再使用 kBinary**：`openFile()` 中仅对 write/append/writeread 使用 `kBinary`，读仍用 `ios_base::in`，与“之前能跑完”的打开方式一致；**写端继续使用 binary**，以保证 geom_reference 写入正确。  
- **Windows 分支条件**：改为 `#if defined(_WIN32) || defined(__MINGW32__)`，确保 MinGW 也走 _stat64，避免 init() 中 seekg(0,end)。  
- **rewindAccessor()**：在 Windows/MinGW 下只读时改为 `seekg(0, ios::beg)`，不再调用 `seekg(0, ios::end)`，避免潜在卡死。

重新编译、安装并复制 DataAccessor 到 isce 后重跑 Step 1；若仍卡死，可查看是否出现 `API init (Win read): NumberOfLines=...` 以判断是否已走 _stat64 路径。

### 10.3 回滚 InterleavedAccessor 以先解决卡死（当前策略）

**结论**：在尝试 _stat64、去掉读端 kBinary、改 rewindAccessor 等后 Step 1 仍卡住，故采用**先回滚、再分步修**的策略。

**已做回滚**：  
- **InterleavedAccessor.cpp** 已恢复为与上游 ISCE2 一致的原始逻辑：无 `_WIN32`/`_stat64` 分支，无 `kBinary`，无调试输出；`init()` 仍用 `seekg(0, ios::end)` + `tellg()` 取文件大小；`rewindAccessor()` 仍用 `seekg(0, ios::end)`。  
- **Topozero.py** 仅去掉调试用 `print`/`flush`，**保留** `setLength`/`createFile`（写端预分配，不影响 DEM 读路径）。

**预期**：回滚后 Step 1 应能跑完（与“之前版本”一致），geom_reference 可能仍为异常值。  
**后续**：在确认无卡死后再单独处理 geom_reference 异常（如仅对**写**使用 binary、或其它不触动读路径的方案）。

### 10.4 数值异常与 GAMMA swap_byte 线索 + 仅写端 binary 修复

**GAMMA 线索**：GAMMA 的 `swap_byte` 用于处理**字节序/二进制解释**问题。用错机器或未做字节序处理时，会出现「数据完全乱掉：数值变成极大/极小值、条纹完全不对、NaN」——与当前 geom_reference 数值异常一致。  
- 若**仅是字节序**：同一份二进制按 LSB 读不对时，按 MSB 读（或反之）应有一端合理；诊断脚本已用 LSB/MSB 分别试过。  
- 文档结论是「LSB 与 MSB 解释均不像合理高程」→ 更可能是**写时二进制被破坏**，而非单纯读端字节序选错。

**根因**：Windows 下 `fstream` 默认**文本模式**写文件时，会把字节 `0x0a` 写成 `0x0d 0x0a`，破坏 float/double 的二进制，导致无论按 LSB 还是 MSB 解释都异常。

**修复（已实现）**：在 **不改动读路径**（避免卡死）的前提下，仅对 **写/追加/读写** 使用二进制模式：  
- `InterleavedAccessor::openFile()` 中，对 `write`/`append`/`writeread`/`readwrite` 的 `fd.open(...)` 增加 `kBinary`（`0x20`）；  
- **读**仍为 `fd.open(..., ios_base::in)`，不做任何改动。  

这样 hgt/lat/lon 等由 topo 写出的二进制不再被文本转换破坏，与 GAMMA 中「保证二进制一致、再谈 swap_byte」的思路一致。  

**验证**：重新编译 DataAccessorLib/DataAccessor、安装、复制到 isce 后重跑 Step 1，再对 `hgt_01.rdr` 跑 `diagnose_topo_byteorder.py`，LSB 应落在合理高程；QGIS 打开 hgt/lat/lon 值域应正常。

### 10.5 数值异常的两个高概率方向（DEM 读取路径）

参考 Grok 总结与 ISCE2/GAMMA 社区经验，数值呈 ±DBL_MAX 或极大/极小常与以下两类原因有关，并在 **DEM→topo** 的读取链上做了对应修复。

**方向 1：DEM 读取产生 NaN/Inf，传播到 geom_reference（高概率）**  
- ISCE2 用 GDAL 读 DEM（VRT/GeoTIFF 等）；若 DEM 的 nodata 为 NaN 或格式兼容性导致 GDAL 读出 NaN，会经 topo 计算传播到 hgt/lat/lon，统计时表现为 ±DBL_MAX。  
- **修复**：在 `DataAccessorPy._gdal_to_bsq_temp()` 中，在将 GDAL 读出的数组写入临时 .bsq 前，用 band 的 `GetNoDataValue()`（或安全默认值 0/-32768）替换所有 NaN/Inf，再写盘。这样 C++/Fortran 读到的 DEM 不再含 NaN，不会向 geom_reference 传播。  
- 源码：`lib/isce2-main/components/iscesys/ImageApi/DataAccessor/DataAccessorPy.py`。

**方向 2：DEM 字节序与 C++ 读取不一致（中低概率）**  
- DEM（如 SRTM .hgt）常为大端；GDAL ReadAsArray 可能按大端返回。C++ InterleavedAccessor 按原生字节序读、不交换，若 .bsq 为大端而在小端机读会乱码→异常值。  
- **修复**：在 `_gdal_to_bsq_temp` 写 .bsq 前，若 `arr.dtype.byteorder` 为大端（`'>'`），先 `arr.byteswap()`，再 `tobytes()` 写入，保证临时文件为机器原生序（Windows/x86 为 LSB），与 C++ 端一致。  
- 同上文件。

**生效**：修改的是 Python 层 `DataAccessorPy.py`；若运行时从 `install/packages/isce` 或 `isce2` 加载，需确保该目录下的 `DataAccessorPy.py` 为最新（重新 `cmake --install` 或手动覆盖）。无需重新编译 C++。

---

## 11. 进一步排查思路（联网检索，数值仍异常时可按此顺序试）

在已做写端 binary、DEM NaN/字节序、setLength/createFile 等修复后，若 geom_reference 数值仍错，可按下述方向逐项排除。

### 11.1 单进程跑 topo，排除 Windows 多进程 spawn 问题

- **依据**：Windows 上 `multiprocessing` 默认用 **spawn**，子进程通过 pickle 传参、不共享内存；若多进程写同一路径或传错对象，可能写出错或状态错乱。  
- **操作**：用 **单进程** 跑 Step 1，确认是否仍异常。  
  - 重新做 stack 初始化时加 `--num_proc4topo 1`（以及 `-n 1` 若需要）；  
  - 或在 `configs/config_run_01_*` 里把 `numProcess` 改为 `1` 后只重跑 run_01。  
- **判断**：若单进程下 hgt/lat/lon 正常，则问题与 Windows 下 topo 多进程（spawn + 文件/accessor）有关，需从改 numProcess 或改 topsStack 调用方式上解决。

### 11.2 核对 VRT 元数据与磁盘二进制是否一致

- **依据**：QGIS/GDAL 按 VRT 里的 **DataType**、**ByteOrder** 解释 .rdr；若 VRT 标成 LSB 而实际为 MSB（或反之），或 DataType 标错，会显示成极大/极小或乱码（类似 ISCE2 issue #509 的 CFLOAT32 标成 FLOAT32）。  
- **操作**：  
  1. 打开 `geom_reference/IW1/hgt_01.rdr.vrt`，确认：  
     - `DataType` 是否为 **Float64**（或与 .rdr 实际一致）；  
     - `ByteOrder` 是否为 **LSB**（Windows/x86 上 topo 写出一般为 LSB）。  
  2. 若曾用工具重生成过 VRT，检查是否误标成 MSB 或其它类型。  
  3. 用诊断脚本或 Python 按 **LSB Float64** 读 .rdr 前若干像素，看数值是否合理；若 LSB 合理而 QGIS 仍错，多半是 VRT 的 ByteOrder/DataType 与文件不一致，改 VRT 或重生成 VRT 使之一致。

### 11.3 对 .rdr 做原始字节级验证（hex / struct）

- **依据**：确认「磁盘上到底写了什么」可区分是写坏还是读/显示错。  
- **操作**：  
  - 用 Python：对 `hgt_01.rdr` 前 8×N 字节 `open(..., 'rb').read()`，用 `struct.unpack('<d', ...)`（LSB）和 `struct.unpack('>d', ...)`（MSB）解出前几个 double，看哪一端像高程（几百～几千米）。  
  - 或用 `xxd` / `Format-Hex` 看前 32 字节的 hex，与「合理高程的 double 的 LSB 表示」对比。  
- **判断**：若 LSB 解出合理而 QGIS 仍异常，问题在 VRT/显示；若 LSB/MSB 解出都异常，问题在写入端（或 DEM 输入→topo 计算链）。

### 11.4 与 Linux 同景同参数对比

- **依据**：ISCE2 官方主要针对 Linux/macOS；若同景、同参数在 Linux 上 topo 正常，而 Windows 异常，可缩小到 Windows 特有（运行库、fstream、多进程、路径等）。  
- **操作**：在 Linux 上跑同一 topsStack 配置与 DEM，对同一 burst 的同一行/列用 Python 读 hgt/lat/lon.rdr，与 Windows 结果逐像素对比。  
- **判断**：若 Linux 正常、Windows 异常，可重点查 Windows 上写端（InterleavedAccessor 写、Fortran→C++ 传参、多进程）；若两边都异常，则更可能是配置/DEM/参数问题。

### 11.5 Fortran–C++ 传参与写缓冲

- **依据**：Fortran 调用 `setLineSequential_r8` 等把 double 传给 C++，C++ 用 `setStream` 写盘；若存在**记录长度头尾**（Fortran unformatted 格式）或**缓冲未 flush**，可能导致错位或尾段未落盘。  
- **当前链**：topo 输出由 C++ InterleavedAccessor 直接写裸字节，无 Fortran 记录标记；若仍怀疑，可在 Fortran 侧打日志看传入的前几行 lat/lon/z 是否合理，或在 C++ setStream 后对前几行写的内容做 hex 打印比对。  

### 11.6 其它可能

- **DEM 源**：若 DEM 来自 GDAL/VRT，可尝试先用 `gdal_translate -ot Float32` 等转为单一类型、显式设 nodata，再给 topo 用，排除 DEM 元数据或类型混乱。  
- **QGIS 显示**：若磁盘上 LSB 已合理，可检查 QGIS 图层属性→符号系统是否用了「估算」统计导致显示异常，改为「实际精度」或手动设最小/最大值再观察。

---

## 12. 排查执行结果（脚本 `scripts/diagnose_geom_troubleshoot.py`）

在路径 `D:\processing\tianfu\processing\geom_reference\IW1` 上执行 11.1～11.3 的结果如下。

### 12.1 11.2 VRT 元数据

- **VRT 文件名**：hgt_01 对应 VRT 为 **`hgt_01.rdr.vrt`**（非 hgt_01.vrt）。
- **结果**：已找到该文件；内容为 **DataType=Float64**、**ByteOrder=LSB**、**SourceFilename=hgt_01.rdr**，与预期一致。故**可排除「VRT 标错导致显示异常」**，问题在 .rdr 文件本身的写入内容。

### 12.2 11.3 原始字节验证（hgt_01.rdr）

- **LSB**：前 16 个 double 的 min/max 为约 ±1e221 量级，**异常**；前 4 个为接近 0 的极小值（显示为 -0.0）。
- **MSB**：同样 min/max 极大/极小，**异常**。
- **前 32 字节 (hex)**：`8f1911e1ce5be3beedf5ddb3915ce3be0b8e54e1ce5be3be6723cb0e0c5be3be`。  
  LSB 解出的第一个 double 为约 -1.09e-231（denormal），非合理高程；说明**磁盘上的二进制本身不是合法高程序列**，非单纯 VRT 标错或显示问题。

**结论**：问题在**写盘内容**——要么写端（Fortran→C++ setStream 或 InterleavedAccessor 写）有误，要么 DEM 输入导致 topo 算出异常值再写入。需在写链上打日志（Fortran 传出前几行 lat/lon/z、C++ setStream 写入的前若干字节）或单进程 + 同景 Linux 对比进一步定位。

### 12.3 11.1 进程数（config）

- **结果**：在 `D:\processing\tianfu\processing\configs` 下未找到 config_run_01*（或目录不存在）。若实际 config 在它处，可手动查 `numProcess` 并改为 1 后单进程重跑 Step 1。`config_reference` 中 [Function-2] topo 的 **numProcess 已为 1**。

### 12.4 排查执行：写链调试 + 单进程 + Docker 脚本

**已做**：  
1. **单进程**：新增 `scripts/run_step1_single_process_then_diagnose.ps1`，会强制 config_run_01* 的 numProcess=1、跑 Step 1、再跑诊断。`config_reference` 里 topo 已为 numProcess : 1。  
2. **写链打日志**：  
   - **Fortran**（`topozero.f90`）：在 `line==1` 时打印 `TOPO_F90 WRITE line=1: z(1:4)=`, `lat(1:4)=`, `lon(1:4)=`。  
   - **C++**（`InterleavedAccessor::setStream`）：前 6 次写入时打印 `API setStream write#N first32bytes <hex>`。  
   需重新编译 topozero + DataAccessor、install、copy 到 isce 后重跑 Step 1，在控制台查看上述输出并与 `diagnose_geom_troubleshoot.py` 的「前 32 字节 hex」对比。  
3. **Docker（Linux）对比**：新增 `scripts/run_step1_and_diagnose_in_docker.ps1`，在容器 **insar-system** 内执行 Step 1 与诊断，将结果写入 `diagnose_result_docker.txt`。用法：确保容器内项目路径一致（默认 `WORK_DIR=$ProjectInContainer/processing`），在宿主机执行该脚本；对比 Windows 与 Docker 输出中的 LSB/first32bytes。

**Step 1 运行中重要现象**：控制台出现 **「Max DEM height: 0.00000000」**，即 Fortran 读到的 DEM 最大值为 0，**整块 DEM 被读成 0**。  
- 若 DEM 实际非零（如 500–5000 m），则说明 **DEM→临时 .bsq→C++/Fortran 读** 这一链在 Windows 上出错（例如 GDAL→BSQ 的字节序/类型/裁剪，或 C++ 读 .bsq 的 offset/size）。  
- DEM 全 0 会导致后续几何与高程计算全部错误，从而写出异常的 hgt/lat/lon。  
**建议**：优先排查 DEM 读链——在 `_gdal_to_bsq_temp` 写临时 .bsq 后，用 Python 读该 .bsq 前若干 float，确认是否为非零高程；并检查 DEM 源文件（.dem/.vrt）在该裁剪区内的值是否非零。

### 12.5 修复：getLine 行号不要二次减 1（已修正）

**背景**：Fortran 侧用 **1-based** 行号调用 `getLine_r4(demAccessor, demline, lineFile)`。`DataAccessorF.cpp` 中的 `getLine_f()` **已**在调用 C++ `getLine(dataLine, *ptLine)` 前执行 `(*ptLine) -= 1`，即传入 C++ 的 `pos` 已是 **0-based**。

**错误修正**：若在 C++ 的 `DataAccessorCaster::getLine` / `DataAccessorNoCaster::getLine` 中再写 `row0 = pos - 1`，会形成**二次转换**：Fortran 传 3755 → F 层变为 3754 → C++ 再减 1 得 3753，读的是错误行；若越界或与预期窗口不符，会出现 **Max DEM height: 0** 或整幅异常。

**正确修改**：C++ `getLine(buf, pos)` 收到的 `pos` 已是 0-based，应直接用作行号：`row0 = (pos >= 0) ? pos : 0`，再以 `row0` 调用 `getData` / `getDataBand`。**不要**在 C++ 中再减 1。

**文件**：`DataAccessorCaster.cpp`、`DataAccessorNoCaster.cpp` 中的 `getLine` / `getLineBand`。

**生效**：重新编译 DataAccessorLib + DataAccessor、`cmake --install`，执行 `scripts/copy_dataaccessor_to_isce.ps1` 将新 `.pyd` 拷入 `packages/isce`。重跑 Step 1 或 `run_topo_burst1_only.ps1` 后，日志中 **Max DEM height** 应为非零，geom_reference 在 QGIS 中应显示合理经纬度与高程。
