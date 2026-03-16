# 阶段 0：Windows 构建环境（路径 A）

本文档记录阶段 0 的完成状态与后续阶段所需的环境准备。

## 已完成（使用项目 `.venv`）

- **Python 虚拟环境**：使用项目根目录下的 `.venv`。
- **Python 扩展后缀**：`EXT_SUFFIX` 为 `.cp311-win_amd64.pyd`，符合 Windows 下构建 Python 扩展的要求。
- **依赖安装**：在 `.venv` 中已安装并验证：
  - `numpy>=1.20`
  - `cython>=0.28.1`
- **验证命令**（在项目根目录执行）：
  ```powershell
  .\.venv\Scripts\python.exe -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))"
  .\.venv\Scripts\python.exe -c "import Cython; print(Cython.__version__)"
  .\.venv\Scripts\python.exe -c "import numpy; print(numpy.__version__)"
  ```

## 阶段 0.2：CMake 与 C/C++ 依赖（进入阶段 1 前需准备）

构建 ISCE2 时需要：

1. **CMake 3.13+**  
   - **已安装**：已通过官方 MSI 安装 CMake 3.30.0 到 `C:\Program Files\CMake`，并已加入**用户 PATH**。新开终端中可直接运行 `cmake --version`。  
   - 验证：`cmake --version`（若刚安装，请新开一个终端再试）

2. **C/C++/Fortran 编译器**（任选其一）  
   - Visual Studio Build Tools + Intel oneAPI Fortran  
   - 或 MinGW-w64 + gfortran（如通过 MSYS2 或 conda-forge 安装）

3. **GDAL、FFTW、HDF5（可选）**  
   - **vcpkg**：安装 vcpkg 后，例如 `vcpkg install gdal fftw3 hdf5`，构建 ISCE2 时使用：  
     `cmake -DCMAKE_TOOLCHAIN_FILE=<vcpkg>/scripts/buildsystems/vcpkg.cmake -B build`  
   - **conda-forge**：若使用 conda 管理环境，可 `conda install -c conda-forge gdal fftw hdf5`，再在 CMake 中通过 `CMAKE_PREFIX_PATH` 指向 conda 环境。

当前阶段 0 的 Python 侧已就绪；进入阶段 1（CMake Windows 配置）前，请确保 CMake 与上述依赖可用。

---

## 阶段 1 已完成（CMake Windows 配置与扩展名）

- **1.1** 已添加 Windows 构建方式：`lib/isce2-main/CMakePresets.json`（win64 / win64-ninja）及 `lib/isce2-main/docs/windows-build.md`。
- **1.2** Motif/X11 已设为可选：根目录 `find_package(Motif QUIET)`，`.cmake/TargetX11.cmake` 中 `find_package(X11 QUIET ...)`，mdx 仅在 Motif/X11 存在时构建。
- **1.3** `.cmake/isce2_helpers.cmake` 中 `isce2_add_cdll` 在 Windows 上使用 `SUFFIX .dll`，否则 `.so`。
- **1.4** 根目录 `CMakeLists.txt` 中：在 UNIX 上保留 `create_symlink`，在 Windows 上改为 `copy_directory` 将 isce2 复制为 isce。

详见 `lib/isce2-main/docs/windows-build.md`。阶段 2 最小 S1 构建需 **FFTW** 与 **Fortran 编译器**，参见 `lib/isce2-main/docs/phase2-requirements-windows.md`。

## 依赖清单文件

- `requirements-phase0.txt`：阶段 0 的 pip 依赖（numpy、cython），已用于 `.venv`。
