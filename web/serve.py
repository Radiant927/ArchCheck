# -*- coding: utf-8 -*-
"""3D viewer 静态文件 + IFC 临时文件的 HTTP 服务。

Streamlit 本身不擅长 serve 静态文件（尤其是 .wasm / .ifc 这种大二进制），
所以单独起一个后台 HTTP server：

  - /viewer/          → web/viewer/ （3D viewer 前端）
  - /ifc/<token>/...  → 临时 IFC 文件目录（每会话一个 token）
  - /health           → 健康检查

用法：
  from web.serve import ViewerServer
  server = ViewerServer()
  server.start()
  url = server.serve_ifc(session_token, ifc_bytes, filename)
  # viewer 页面：f"{server.base_url}/viewer/?ifc={url}"
"""
import os
import threading
import uuid
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
VIEWER_DIR = ROOT / "web" / "viewer"
TMP_DIR = ROOT / "output" / "viewer_tmp"


def _write_ifc_to_tmp(session_token, ifc_bytes, filename, base_url):
    """把 IFC 写到公共临时目录，返回可访问的 URL。"""
    session_dir = TMP_DIR / session_token
    session_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_"
                         for c in filename)
    file_path = session_dir / safe_name
    file_path.write_bytes(ifc_bytes)
    return f"{base_url}/ifc/{session_token}/{safe_name}"


MIME_MAP = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".wasm": "application/wasm",
    ".ifc": "application/octet-stream",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def _mime(path_str):
    import os
    _, ext = os.path.splitext(path_str)
    return MIME_MAP.get(ext.lower(), "application/octet-stream")


class _Handler(SimpleHTTPRequestHandler):
    """URL 路由：
    /viewer/* → VIEWER_DIR/*
    /ifc/*    → TMP_DIR/*
    """

    def do_GET(self):
        path = urlparse(self.path).path
        path = unquote(path)

        # 路由映射到文件系统路径
        fs_path = None
        if path == "/" or path == "":
            self.send_response(302)
            self.send_header("Location", "/viewer/")
            self.end_headers_with_cors()
            return
        if path == "/health":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers_with_cors()
            self.wfile.write(body)
            return
        if path.startswith("/api/"):
            # /api/<name>?session=<tok> → TMP_DIR/<tok>/<name>.json
            from urllib.parse import parse_qs
            name = path[len("/api/"):] or "violations"
            name = "".join(c for c in name if c.isalnum() or c in "_-")
            params = parse_qs(urlparse(self.path).query)
            session = (params.get("session", ["default"])[0] or "default")
            safe_session = "".join(c for c in session if c.isalnum() or c in "_-")
            vfile = TMP_DIR / safe_session / f"{name}.json"
            if vfile.is_file():
                data = vfile.read_bytes()
            else:
                data = b"{}" if name == "elements" else b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers_with_cors()
            self.wfile.write(data)
            return
        if path == "/viewer" or path == "/viewer/":
            fs_path = VIEWER_DIR / "index.html"
        elif path.startswith("/viewer/"):
            sub = path[len("/viewer/"):]
            # 防目录穿越
            if ".." in sub or sub.startswith("/"):
                self.send_error(400, "Bad path")
                return
            fs_path = VIEWER_DIR / sub
            if fs_path.is_dir():
                fs_path = fs_path / "index.html"
        elif path.startswith("/ifc/"):
            sub = path[len("/ifc/"):]
            if ".." in sub or sub.startswith("/"):
                self.send_error(400, "Bad path")
                return
            fs_path = TMP_DIR / sub
        else:
            self.send_error(404, "Not found")
            return

        if not fs_path or not fs_path.is_file():
            self.send_error(404, f"File not found: {path}")
            return

        try:
            data = fs_path.read_bytes()
        except Exception as e:
            self.send_error(500, str(e))
            return

        self.send_response(200)
        self.send_header("Content-Type", _mime(str(fs_path)))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers_with_cors()
        self.wfile.write(data)

    def end_headers_with_cors(self):
        # 只开放跨域，不设 COOP/COEP —— 一旦 crossOriginIsolated=true，
        # web-ifc 会走多线程 wasm 路径（web-ifc-mt.worker.js），而该文件
        # npm 包未提供，会导致模型加载卡死。保持单线程 wasm 路径。
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def log_message(self, format, *args):
        return


class ViewerServer:
    def __init__(self, port=8765):
        self.port = port
        self._server = None
        self._thread = None
        TMP_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.port}"

    @property
    def viewer_url(self):
        return f"{self.base_url}/viewer/"

    def start(self):
        if self._server is not None:
            return
        self._server = HTTPServer(("127.0.0.1", self.port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"[viewer-server] running on {self.base_url}")

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None

    def serve_ifc(self, session_token, ifc_bytes, filename):
        return _write_ifc_to_tmp(session_token, ifc_bytes, filename, self.base_url)

    def cleanup_session(self, session_token):
        """会话结束时清理临时文件。"""
        import shutil
        session_dir = TMP_DIR / session_token
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)


# 单例
_instance = None


def _port_in_use(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


class _ProxyServer:
    """端口上已经有 viewer server 在跑了（可能是另一个进程起的），
    直接用代理对象提供相同接口。IFC 文件通过写公共目录共享。"""
    def __init__(self, port):
        self.port = port
        self.base_url = f"http://127.0.0.1:{port}"
        self.viewer_url = f"{self.base_url}/viewer"

    def start(self):
        pass

    def stop(self):
        pass

    def serve_ifc(self, session_token, ifc_bytes, filename):
        return _write_ifc_to_tmp(session_token, ifc_bytes, filename, self.base_url)


def get_server(port=8765):
    global _instance
    if _instance is not None:
        return _instance
    if _port_in_use(port):
        # 端口已在监听——直接连接已有的 viewer server
        _instance = _ProxyServer(port)
        return _instance
    _instance = ViewerServer(port=port)
    _instance.start()
    return _instance
