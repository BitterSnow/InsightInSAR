"""
从包含 self.files = [ "https://...zip", ... ] 的 Python 文件中提取下载链接，
与本地目录对比：已存在的创建硬链接到目标目录，未下载的写入待下载列表。
"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

# 匹配 self.files = [ ... ] 中的 "https://...zip" 或 'https://...zip'
_LINK_PATTERN = re.compile(r'["\'](https://[^\s"\']+\.zip)["\']')


def extract_links_from_code(file_path: str) -> List[str]:
    """
    从包含 self.files = [ "https://...", ... ] 的 Python 文件中提取所有 .zip 下载链接。
    支持跨行、缩进、双引号/单引号；尝试 UTF-8，失败则 latin1。
    """
    for encoding in ("utf-8", "latin1"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, OSError) as e:
            logger.debug("read %s with %s: %s", file_path, encoding, e)
            continue
    else:
        raise ValueError(f"无法以 UTF-8 或 Latin1 读取文件: {file_path}")

    one_line = re.sub(r"\s+", " ", content).strip()
    matches = _LINK_PATTERN.findall(one_line)
    return list(dict.fromkeys(matches))  # 去重且保持顺序


def run_new_data_to_download(
    download_list_file: str,
    local_folder: str,
    output_file: str,
    symlink_folder: str,
) -> Tuple[int, int, List[str]]:
    """
    主流程：提取链接 -> 与本地对比 -> 已存在则建硬链接，缺失则写入 output_file。

    Returns:
        (总链接数, 已存在并建链数, 创建硬链接时的错误信息列表)
    """
    if not os.path.isfile(download_list_file):
        raise FileNotFoundError(f"下载列表文件不存在: {download_list_file}")

    all_links = extract_links_from_code(download_list_file)
    remote_filenames = {os.path.basename(link): link for link in all_links}

    if not os.path.isdir(local_folder):
        raise FileNotFoundError(f"本地数据目录不存在: {local_folder}")
    os.makedirs(symlink_folder, exist_ok=True)
    local_files = set(os.listdir(local_folder))

    missing_links: List[str] = []
    existing_count = 0
    link_errors: List[str] = []

    for filename, link in remote_filenames.items():
        if filename in local_files:
            src_path = os.path.abspath(os.path.join(local_folder, filename))
            dst_link = os.path.join(symlink_folder, filename)
            try:
                if os.path.exists(dst_link):
                    os.remove(dst_link)
                os.link(src_path, dst_link)
                existing_count += 1
            except OSError as e:
                msg = f"创建硬链接失败 {dst_link}: {e}"
                link_errors.append(msg)
                logger.warning(msg)
        else:
            missing_links.append(link)

    with open(output_file, "w", encoding="utf-8") as f:
        for link in missing_links:
            f.write(link + "\n")

    return len(all_links), existing_count, link_errors
