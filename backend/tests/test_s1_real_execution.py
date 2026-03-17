"""
真实数据执行测试：使用 D:\coding\insar-system\data 目录下的真实数据执行完整的 S1 处理流程。
注意：此测试会实际执行 ISCE2 处理，可能需要较长时间。
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

CONTAINER_DATA_ROOT = "/app/data"
IN_CONTAINER = os.path.exists(CONTAINER_DATA_ROOT)
DATA_ROOT = Path(CONTAINER_DATA_ROOT) if IN_CONTAINER else Path("D:/coding/insar-system/data")


def find_data_files():
    """查找数据文件"""
    data_root = DATA_ROOT
    radar_dir = data_root / "radar"
    zip_files = list(radar_dir.glob("S1A_IW_SLC*.zip")) if radar_dir.exists() else []
    target_shp = data_root / "target.shp"
    dem_dir = data_root / "dem"
    dem_files = list(dem_dir.glob("*.dem")) if dem_dir.exists() else []
    orbit_dir = data_root / "orbit"
    aux_dir = data_root / "auxcal"
    
    return {
        "zip_file": zip_files[0] if zip_files else None,
        "target_shp": target_shp if target_shp.exists() else None,
        "dem_file": dem_files[0] if dem_files else None,
        "orbit_dir": orbit_dir if orbit_dir.exists() else None,
        "aux_dir": aux_dir if aux_dir.exists() else None,
    }


def test_real_execution():
    """执行真实的 S1 处理（仅处理第一个 swath，快速验证）"""
    print("=" * 60)
    print("真实数据执行测试")
    print("=" * 60)
    print(f"运行环境: {'容器内' if IN_CONTAINER else '宿主机'}")
    
    files = find_data_files()
    if not all([files["zip_file"], files["target_shp"], files["dem_file"], files["orbit_dir"], files["aux_dir"]]):
        print("✗ 缺少必要文件")
        return False
    
    # 转换为容器路径
    def to_container_path(p: Path) -> str:
        if IN_CONTAINER:
            return str(p)
        host_str = str(p).replace("\\", "/")
        host_root = str(Path("D:/coding/insar-system/data")).replace("\\", "/")
        if host_str.startswith(host_root):
            relative = host_str[len(host_root):].lstrip("/")
            return f"{CONTAINER_DATA_ROOT}/{relative}"
        return host_str
    
    zip_container = to_container_path(files["zip_file"])
    dem_container = to_container_path(files["dem_file"])
    orbit_container = to_container_path(files["orbit_dir"])
    aux_container = to_container_path(files["aux_dir"])
    target_shp_container = to_container_path(files["target_shp"])
    
    print(f"\n数据文件:")
    print(f"  ZIP: {zip_container}")
    print(f"  DEM: {dem_container}")
    print(f"  轨道: {orbit_container}")
    print(f"  Aux: {aux_container}")
    print(f"  target.shp: {target_shp_container}")
    
    # 检测 subswath
    try:
        from backend.scripts.subswath_detector import detect_subswaths
        print("\n检测 subswath...")
        swaths = detect_subswaths(zip_container, shapefile_path=target_shp_container)
        print(f"✓ 检测到需要处理的 subswath: {swaths}")
    except Exception as e:
        print(f"⚠ Subswath 检测失败: {e}")
        print("  使用默认 swath [1]")
        swaths = [1]
    
    # 创建请求
    from shared_models import InSARTaskRequest
    request = InSARTaskRequest(
        zip_path=zip_container,
        orbit_dir=orbit_container,
        dem_path=dem_container,
        aux_dir=aux_container,
        target_shp_path=target_shp_container,
        swaths=" ".join(map(str, swaths)),
        polarization="vv",
    )
    
    # 执行处理（仅第一个 swath，快速验证）
    print(f"\n开始处理（仅 swath {swaths[0]} 用于快速验证）...")
    print("  注意: 完整处理可能需要数分钟")
    
    try:
        from backend.services.s1_processing_service import run_s1_import_from_request
        
        progress_log = []
        def progress_cb(pct: float, msg: str):
            progress_log.append((pct, msg))
            print(f"  [{pct:.1f}%] {msg}")
        
        result = run_s1_import_from_request(request, progress_callback=progress_cb)
        
        print("\n" + "=" * 60)
        print("处理结果")
        print("=" * 60)
        print(f"成功: {result.get('success', False)}")
        if result.get("success"):
            print(f"生成的 SLC/VRT 文件:")
            for path in result.get("slc_vrt_paths", []):
                print(f"  {path}")
            print(f"\n元数据: {result.get('metadata', {})}")
        else:
            print(f"错误: {result.get('error_message', 'Unknown error')}")
        
        return result.get("success", False)
    except Exception as e:
        print(f"\n✗ 处理失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if not IN_CONTAINER:
        print("⚠ 警告: 此测试应在容器内运行")
        print("  在宿主机运行可能因缺少 ISCE2 而失败")
        response = input("  是否继续? (y/N): ")
        if response.lower() != "y":
            sys.exit(0)
    
    success = test_real_execution()
    sys.exit(0 if success else 1)
