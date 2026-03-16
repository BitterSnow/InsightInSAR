#!/usr/bin/env python3
"""测试仅支持 Windows 绝对路径建项目。"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)
# 任意绝对路径（例如 D 盘下某目录）
path = "D:/coding/insar-system/data/anywhere_proj"
r = client.post(
    "/api/projects",
    json={"name": "anywhere", "radar_type": "Sentinel-1", "project_path": path},
)
print("Status:", r.status_code)
print("Response:", r.json() if r.content else r.text)
if r.status_code != 200:
    sys.exit(1)
data = r.json()
fp = data.get("file_path", "").replace("/", os.sep)
print("File exists:", os.path.isfile(fp))
print("本机模式（任意路径）测试通过。")
