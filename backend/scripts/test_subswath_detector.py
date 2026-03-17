#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试Subswath检测器
"""

import sys
from pathlib import Path

# 添加scripts目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from subswath_detector import detect_subswaths


def main():
    """运行测试"""
    # 测试数据路径
    base_dir = Path(__file__).parent.parent.parent
    data_dir = base_dir / 'data' / 'raw'
    
    sentinel1_zip = data_dir / 'S1A_IW_SLC__1SDV_20200714T231403_20200714T231430_033457_03E080_5554.zip'
    shapefile = data_dir / 'target.shp'
    
    print("=" * 60)
    print("Sentinel-1 Subswath检测器测试")
    print("=" * 60)
    print(f"\nSentinel-1数据: {sentinel1_zip}")
    print(f"任务区shapefile: {shapefile}")
    print()
    
    # 检查文件是否存在
    if not sentinel1_zip.exists():
        print(f"错误: Sentinel-1数据文件不存在: {sentinel1_zip}")
        return 1
    
    if not shapefile.exists():
        print(f"错误: Shapefile文件不存在: {shapefile}")
        return 1
    
    try:
        # 运行检测
        result = detect_subswaths(
            str(sentinel1_zip),
            shapefile_path=str(shapefile),
        )
        
        print("\n" + "=" * 60)
        print("测试结果")
        print("=" * 60)
        print(f"需要处理的subswath: {result}")
        print(f"结果类型: {type(result).__name__}")
        print(f"结果长度: {len(result)}")
        
        if result:
            print(f"\n需要处理 {len(result)} 个subswath: {', '.join(map(str, result))}")
        else:
            print("\n没有subswath与任务区相交")
        
        print("\n测试完成！")
        return 0
        
    except Exception as e:
        print(f"\n错误: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
