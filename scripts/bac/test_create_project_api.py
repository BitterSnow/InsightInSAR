#!/usr/bin/env python3
"""使用 TestClient 测试新建工程 API（无需启动 uvicorn）。"""
import os
import sys
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data").replace("\\", "/")
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("INSAR_DATA_ROOT", DATA_DIR)

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    project_path = f"{DATA_DIR}/test_e2e"
    payload = {
        "name": "test_e2e",
        "radar_type": "Sentinel-1",
        "project_path": project_path,
    }
    resp = client.post("/api/projects", json=payload)
    print("Status:", resp.status_code)
    print("Response:", resp.json() if resp.content else resp.text)

    if resp.status_code != 200:
        print("失败: 预期 200")
        return 1

    data = resp.json()
    file_path = data.get("file_path", "").replace("/", os.sep)
    if not os.path.isabs(file_path) or not file_path.startswith(os.path.abspath(DATA_DIR).replace("/", os.sep)):
        file_path = os.path.join(DATA_DIR.replace("/", os.sep), "test_e2e", "test_e2e.md")
    if os.path.isfile(file_path):
        print("已创建工程文件:", file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            print("文件内容:\n", content)
        if "项目名称" in content and "test_e2e" in content and "项目id" in content:
            print("新建工程功能测试通过。")
            return 0
    print("未找到或内容不符合预期")
    return 1


if __name__ == "__main__":
    sys.exit(main())
