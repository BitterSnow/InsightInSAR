#!/usr/bin/env python3
"""测试新建工程 API：启动服务并调用 POST /api/projects，检查 .md 文件是否生成。"""
import os
import sys
import time
import subprocess
import urllib.request
import urllib.error
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
API_URL = "http://127.0.0.1:8000/api/projects"
ENV = os.environ.copy()
ENV["PYTHONPATH"] = PROJECT_ROOT
ENV["INSAR_DATA_ROOT"] = DATA_DIR.replace("\\", "/")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    python = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    if not os.path.isfile(python):
        python = sys.executable

    proc = subprocess.Popen(
        [python, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=PROJECT_ROOT,
        env=ENV,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(30):
            try:
                req = urllib.request.Request(
                    API_URL,
                    data=json.dumps({
                        "name": "test_project",
                        "radar_type": "Sentinel-1",
                        "project_path": DATA_DIR.replace("\\", "/") + "/test_project",
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = json.loads(resp.read().decode())
                    print("API 响应:", json.dumps(data, ensure_ascii=False, indent=2))
                    break
            except (urllib.error.URLError, OSError):
                time.sleep(0.5)
        else:
            print("错误: 等待 API 超时")
            return 1

        file_path = data.get("file_path", "").replace("/", os.sep)
        if not os.path.isfile(file_path):
            # 尝试容器路径风格转本地
            file_path = os.path.join(DATA_DIR, "test_project", "test_project.md")
        if os.path.isfile(file_path):
            print("已创建工程文件:", file_path)
            with open(file_path, "r", encoding="utf-8") as f:
                print("文件内容预览:\n", f.read()[:500])
        else:
            print("未找到工程文件，响应 file_path:", data.get("file_path"))
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(main())
