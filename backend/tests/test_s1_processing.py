"""
测试 ISCE2 Sentinel-1 处理逻辑：验证 s1_processing_service 能否正确导入和使用 ISCE2 API。
可在容器内运行：docker compose exec worker python3 -m backend.tests.test_s1_processing
"""
import os
import sys

# 确保能找到项目模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


def test_isce2_import():
    """测试能否导入 ISCE2 Sentinel1 类"""
    print("=" * 60)
    print("测试 1: ISCE2 Sentinel1 导入")
    print("=" * 60)
    try:
        from isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
        print("✓ ISCE2 Sentinel1 导入成功 (标准路径)")
        print(f"  类: {Sentinel1}")
        print(f"  模块路径: {Sentinel1.__module__}")
        return True
    except ImportError:
        try:
            from isce.components.isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
            print("✓ ISCE2 Sentinel1 导入成功 (conda 环境路径)")
            print(f"  类: {Sentinel1}")
            print(f"  模块路径: {Sentinel1.__module__}")
            return True
        except ImportError:
            try:
                from isce2.components.isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
                print("✓ ISCE2 Sentinel1 导入成功 (Windows install/packages)")
                print(f"  类: {Sentinel1}")
                print(f"  模块路径: {Sentinel1.__module__}")
                return True
            except ImportError as e:
                print(f"✗ ISCE2 Sentinel1 导入失败: {e}")
                print("  提示: 请在 insar-ubuntu20 容器内运行，或本机设置 PYTHONPATH=lib/isce2-main/install/packages 并使用 isce2-build Python")
                return False


def test_sentinel1_configure():
    """测试 Sentinel1 对象创建与配置"""
    print("\n" + "=" * 60)
    print("测试 2: Sentinel1 对象创建与配置")
    print("=" * 60)
    try:
        try:
            from isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
        except ImportError:
            try:
                from isce.components.isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
            except ImportError:
                from isce2.components.isceobj.Sensor.TOPS.Sentinel1 import Sentinel1
        obj = Sentinel1()
        obj.configure()
        print("✓ Sentinel1 对象创建成功")
        print(f"  默认 swathNumber: {obj.swathNumber}")
        print(f"  默认 polarization: {obj.polarization}")
        print(f"  默认 output: {obj.output}")
        return True
    except Exception as e:
        print(f"✗ Sentinel1 对象创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_service_module_import():
    """测试 s1_processing_service 模块导入"""
    print("\n" + "=" * 60)
    print("测试 3: s1_processing_service 模块导入")
    print("=" * 60)
    try:
        from backend.services.s1_processing_service import (
            run_sentinel1_extract,
            run_s1_import_from_request,
            resolve_region_of_interest,
            bbox_from_shapefile,
        )
        print("✓ s1_processing_service 模块导入成功")
        print(f"  run_sentinel1_extract: {run_sentinel1_extract}")
        print(f"  run_s1_import_from_request: {run_s1_import_from_request}")
        return True
    except Exception as e:
        print(f"✗ s1_processing_service 模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_shared_models_import():
    """测试 shared_models 导入"""
    print("\n" + "=" * 60)
    print("测试 4: shared_models 导入")
    print("=" * 60)
    try:
        from shared_models import InSARTaskRequest, InSARProgressUpdate, InSARTaskResult
        print("✓ shared_models 导入成功")
        
        # 测试创建请求对象
        req = InSARTaskRequest(
            zip_path="/app/data/slc/test.zip",
            orbit_dir="/app/data/orbits",
            dem_path="/app/data/dem/dem.wgs84",
            aux_dir="/app/data/aux",
            swaths="1 2 3",
            polarization="vv",
        )
        print(f"  InSARTaskRequest 创建成功: zip_path={req.zip_path}")
        return True
    except Exception as e:
        print(f"✗ shared_models 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_celery_task_import():
    """测试 Celery 任务模块导入"""
    print("\n" + "=" * 60)
    print("测试 5: Celery 任务模块导入")
    print("=" * 60)
    try:
        from backend.app.celery_app import app as celery_app
        from backend.app.tasks import run_s1_import_task
        print("✓ Celery 任务模块导入成功")
        print(f"  Celery app: {celery_app}")
        print(f"  任务名称: {run_s1_import_task.name}")
        return True
    except Exception as e:
        print(f"✗ Celery 任务模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_roi_resolution():
    """测试 ROI 解析逻辑（不依赖实际文件）"""
    print("\n" + "=" * 60)
    print("测试 6: ROI 解析逻辑")
    print("=" * 60)
    try:
        from backend.services.s1_processing_service import resolve_region_of_interest
        
        # 测试 bbox_snwe
        roi1 = resolve_region_of_interest(None, [19.0, 20.0, -99.5, -98.5])
        assert len(roi1) == 4, f"Expected 4 values, got {len(roi1)}"
        assert roi1 == [19.0, 20.0, -99.5, -98.5], f"ROI mismatch: {roi1}"
        print(f"✓ bbox_snwe 解析成功: {roi1}")
        
        # 测试空值
        roi2 = resolve_region_of_interest(None, None)
        assert roi2 == [], f"Expected empty list, got {roi2}"
        print("✓ 空 ROI 处理正确")
        
        return True
    except Exception as e:
        print(f"✗ ROI 解析测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("ISCE2 Sentinel-1 处理逻辑测试")
    print("=" * 60)
    print(f"Python: {sys.version}")
    print(f"工作目录: {os.getcwd()}")
    print(f"PYTHONPATH: {os.environ.get('PYTHONPATH', '(未设置)')}")
    
    results = []
    results.append(("ISCE2 导入", test_isce2_import()))
    results.append(("Sentinel1 配置", test_sentinel1_configure()))
    results.append(("服务模块导入", test_service_module_import()))
    results.append(("共享模型导入", test_shared_models_import()))
    results.append(("Celery 任务导入", test_celery_task_import()))
    results.append(("ROI 解析", test_roi_resolution()))
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"{status} {name}")
    print(f"\n通过: {passed}/{total}")
    
    if passed == total:
        print("\n✓ 所有测试通过！ISCE2 处理逻辑已正确封装。")
        return 0
    else:
        print(f"\n✗ {total - passed} 个测试失败，请检查环境配置。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
