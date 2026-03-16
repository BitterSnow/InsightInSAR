#!/usr/bin/env python3
"""
本地文件夹选择服务（Windows 宿主上运行）。
在浏览器中点击「打开文件夹」时，前端会请求本服务，弹出系统文件夹选择框并返回完整路径。
仅需在需要「项目路径」显示完整路径时，在 Windows 上运行: python scripts/select_folder_server.py
"""
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

HAS_TK = False
try:
    from tkinter import Tk, filedialog
    HAS_TK = True
except Exception:
    pass

HOST = "127.0.0.1"
PORT = 8765


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/select", "/select/"):
            path = ""
            if HAS_TK:
                root = Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                path = filedialog.askdirectory(title="选择项目路径")
                try:
                    root.destroy()
                except Exception:
                    pass
            else:
                sys.stderr.write("tkinter 不可用，无法弹出文件夹选择框\n")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"path": path or ""}).encode("utf-8"))
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass


def main():
    if not HAS_TK:
        print("未安装或无法加载 tkinter，无法弹出文件夹选择框。请确保在带图形界面的 Windows 上运行。", file=sys.stderr)
    print(f"文件夹选择服务: http://{HOST}:{PORT}/select")
    print("前端将请求此地址以获取完整路径，关闭本窗口即停止服务。")
    HTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
