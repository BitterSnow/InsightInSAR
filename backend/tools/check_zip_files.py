"""
检查指定目录下所有 .zip 文件是否可正常打开（zipfile 校验）。
返回完整列表与错误列表，便于桌面端展示。
"""
from __future__ import annotations

import logging
import os
import zipfile
from typing import List, Tuple

logger = logging.getLogger(__name__)


def run_check_zip_files(local_folder: str) -> Tuple[List[str], List[str]]:
    """
    扫描目录下所有包含 'zip' 的文件名，尝试用 zipfile 打开。
    仅当扩展名为 .zip 时进行校验（可选：也可对含 'zip' 的均尝试，与原文一致则对含 zip 的均尝试）。

    Returns:
        (正确列表, 错误列表) 文件名（不含路径）
    """
    if not os.path.isdir(local_folder):
        raise FileNotFoundError(f"目录不存在: {local_folder}")

    correct: List[str] = []
    errors: List[str] = []
    for name in os.listdir(local_folder):
        if "zip" not in name.lower():
            continue
        path = os.path.join(local_folder, name)
        if not os.path.isfile(path):
            continue
        try:
            with zipfile.ZipFile(path, "r") as zf:
                pass  # 仅校验能否正常打开
            correct.append(name)
        except (zipfile.BadZipFile, OSError) as e:
            logger.debug("zip error %s: %s", name, e)
            errors.append(name)
    return correct, errors
