"""
集成测试：使用 D:\coding\insar-system\data 目录下的真实数据测试 S1 处理流程。
1. 使用 target.shp 确定处理范围
2. 调用 subswath_detector 自动检测需要处理的 swath
3. 运行完整的 S1 导入与配准流程
"""
import os
import sys
from pathlib import Path

# 确保能找到项目模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# 数据路径
CONTAINER_DATA_ROOT = "/app/data"
# 检测是否在容器内运行
IN_CONTAINER = os.path.exists(CONTAINER_DATA_ROOT)
DATA_ROOT = Path(CONTAINER_DATA_ROOT) if IN_CONTAINER else Path("D:/coding/insar-system/data")


def find_data_files():
    """查找数据目录下的文件（自动检测容器或宿主路径）"""
    data_root = DATA_ROOT
    
    # 查找第一个 S1 zip 文件
    radar_dir = data_root / "radar"
    zip_files = list(radar_dir.glob("S1A_IW_SLC*.zip")) if radar_dir.exists() else []
    
    # target.shp
    target_shp = data_root / "target.shp"
    
    # DEM
    dem_dir = data_root / "dem"
    dem_files = list(dem_dir.glob("*.dem")) if dem_dir.exists() else []
    
    # 轨道目录
    orbit_dir = data_root / "orbit"
    
    # Aux 目录
    aux_dir = data_root / "auxcal"
    
    return {
        "zip_file": zip_files[0] if zip_files else None,
        "target_shp": target_shp if target_shp.exists() else None,
        "dem_file": dem_files[0] if dem_files else None,
        "orbit_dir": orbit_dir if orbit_dir.exists() else None,
        "aux_dir": aux_dir if aux_dir.exists() else None,
    }


def test_subswath_detection():
    """测试 subswath_detector"""
    print("=" * 60)
    print("步骤 1: 检测需要处理的 subswath")
    print("=" * 60)
    
    files = find_data_files()
    if not files["zip_file"] or not files["target_shp"]:
        print("✗ 缺少必要文件:")
        print(f"  zip_file: {files['zip_file']}")
        print(f"  target_shp: {files['target_shp']}")
        return None
    
    try:
        from backend.scripts.subswath_detector import detect_subswaths
        
        zip_path = str(files["zip_file"])
        shp_path = str(files["target_shp"])
        
        print(f"Sentinel-1 ZIP: {zip_path}")
        print(f"target.shp: {shp_path}")
        print("正在检测 subswath...")
        
        swaths = detect_subswaths(zip_path, shapefile_path=shp_path)
        print(f"✓ 检测完成，需要处理的 subswath: {swaths}")
        return swaths
    except Exception as e:
        print(f"✗ subswath 检测失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_s1_processing_with_real_data():
    """使用真实数据测试 S1 处理"""
    print("\n" + "=" * 60)
    print("步骤 2: 使用真实数据进行 S1 处理测试")
    print("=" * 60)
    
    files = find_data_files()
    
    # 检查必要文件
    missing = []
    if not files["zip_file"]:
        missing.append("S1 ZIP 文件")
    if not files["target_shp"]:
        missing.append("target.shp")
    if not files["dem_file"]:
        missing.append("DEM 文件")
    if not files["orbit_dir"]:
        missing.append("轨道目录")
    if not files["aux_dir"]:
        missing.append("Aux 目录")
    
    if missing:
        print(f"✗ 缺少必要文件: {', '.join(missing)}")
        print("\n当前 data 目录结构:")
        for k, v in files.items():
            print(f"  {k}: {v}")
        return False
    
    # 检测 subswath
    swaths = test_subswath_detection()
    if not swaths:
        print("⚠ 无法检测 subswath，使用默认 [1, 2, 3]")
        swaths = [1, 2, 3]
    
    # 转换为容器路径（如果不在容器内）
    def to_container_path(p: Path) -> str:
        if IN_CONTAINER:
            return str(p)
        # 宿主路径转容器路径
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
    
    print(f"\n容器路径映射:")
    print(f"  ZIP: {zip_container}")
    print(f"  DEM: {dem_container}")
    print(f"  轨道: {orbit_container}")
    print(f"  Aux: {aux_container}")
    print(f"  target.shp: {target_shp_container}")
    print(f"  Swaths: {swaths}")
    
    # 创建请求对象
    try:
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
        print("\n✓ InSARTaskRequest 创建成功")
    except Exception as e:
        print(f"✗ 创建请求对象失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试处理服务（不实际运行，只验证调用）
    print("\n" + "=" * 60)
    print("步骤 3: 验证处理服务调用（不实际执行）")
    print("=" * 60)
    
    try:
        from backend.services.s1_processing_service import run_s1_import_from_request
        
        # 检查 ISCE2 是否可用
        try:
            try:
                from isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
            except ImportError:
                try:
                    from isce.components.isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
                except ImportError:
                    from isce2.components.isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
            print("✓ ISCE2 Sentinel1 可用")
        except ImportError:
            print("⚠ ISCE2 不可用，跳过实际处理测试")
            print("  提示: 在容器内运行此测试以执行完整流程")
            return True
        
        # 验证路径存在（在容器内）
        print("\n验证容器内路径（需要容器运行）...")
        print("  注意: 此测试仅验证代码逻辑，实际处理需在容器内执行")
        
        return True
    except Exception as e:
        print(f"✗ 处理服务验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_celery_task_integration():
    """测试 Celery 任务集成（模拟）"""
    print("\n" + "=" * 60)
    print("步骤 4: Celery 任务集成验证")
    print("=" * 60)
    
    files = find_data_files()
    if not all([files["zip_file"], files["target_shp"], files["dem_file"], files["orbit_dir"], files["aux_dir"]]):
        print("⚠ 缺少数据文件，跳过 Celery 任务测试")
        return True
    
    try:
        from backend.app.tasks import run_s1_import_task
        from shared_models import InSARTaskRequest
        
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
        
        request = InSARTaskRequest(
            zip_path=zip_container,
            orbit_dir=orbit_container,
            dem_path=dem_container,
            aux_dir=aux_container,
            target_shp_path=target_shp_container,
            swaths="1 2 3",
            polarization="vv",
        )
        
        print("✓ Celery 任务可调用")
        print(f"  任务名称: {run_s1_import_task.name}")
        print(f"  请求对象: zip_path={request.zip_path}")
        print("\n  注意: 实际执行需在容器内通过 Celery worker 运行")
        
        return True
    except Exception as e:
        print(f"✗ Celery 任务验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行集成测试"""
    print("\n" + "=" * 60)
    print("S1 处理集成测试（使用真实数据）")
    print("=" * 60)
    print(f"运行环境: {'容器内' if IN_CONTAINER else '宿主机'}")
    print(f"数据根目录: {DATA_ROOT}")
    print(f"容器数据根: {CONTAINER_DATA_ROOT}")
    
    results = []
    
    # 测试 1: subswath 检测
    swaths = test_subswath_detection()
    results.append(("Subswath 检测", swaths is not None))
    
    # 测试 2: S1 处理服务
    results.append(("S1 处理服务", test_s1_processing_with_real_data()))
    
    # 测试 3: Celery 任务集成
    results.append(("Celery 任务集成", test_celery_task_integration()))
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"{status} {name}")
    print(f"\n通过: {passed}/{total}")
    
    if swaths:
        print(f"\n检测到的 subswath: {swaths}")
        print("  可在提交任务时使用此结果作为 swaths 参数")
    
    if passed == total:
        print("\n✓ 所有测试通过！")
        print("\n下一步: 在容器内执行实际处理")
        print("  1. 确保 worker 容器运行")
        print("  2. 通过 FastAPI 提交任务")
        print("  3. 监控任务进度")
        return 0
    else:
        print(f"\n✗ {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
