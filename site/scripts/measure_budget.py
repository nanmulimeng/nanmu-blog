# -*- coding: utf-8 -*-
"""site 资源预算测量(Playwright/Chromium;入库可复跑,只报实测数)。

口径(INTEGRATION-PLAN §5):
  A. 冷缓存分型——全新 context 首访内页,按 html/css/js/woff2 分类合计
     响应字节(本地无压缩,即原始字节);
  B. 跨页面新增——同 context 再访问其余三页,统计新增 .woff2 请求数
     与新增字节(衡量字体分片的按需命中,不重复计数);
  C. fonts.css 原始与 gzip 传输体积(磁盘文件实测)。
用法:python -I site/scripts/measure_budget.py [--port 8936]
"""
import gzip
import http.server
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = 8936
SITE = Path(__file__).resolve().parents[1]  # site/
CHROME = (r"C:\Users\nanmu\AppData\Local\ms-playwright\chromium-1248"
          r"\chrome-win64\chrome.exe")


def serve(root):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass
    class TS(socketserver.ThreadingTCPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            pass  # 本地测量:连接中断噪声不值得打印
    socketserver.TCPServer.allow_reuse_address = True
    httpd = TS(("127.0.0.1", PORT), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def classify(url):
    for kind, ext in (("woff2", ".woff2"), ("css", ".css"), ("js", ".js"),
                      ("html", (".html", "/"))):
        if url.endswith(ext):
            return kind
    return "other"


def size_of(r):
    """响应字节:content-length 头优先(本地 server 恒有),退 body()。"""
    cl = r.headers.get("content-length")
    if cl and cl.isdigit():
        return int(cl)
    try:
        return len(r.body())
    except Exception:  # noqa: BLE001 本地服务,仅统计
        return 0


def fetch_bytes(page, url, seen):
    """访问 url,返回 (本页分类字节, 新增 woff2 数, 新增 woff2 字节)。"""
    page_bytes = {}
    new_shards = 0
    new_bytes = 0

    def on_resp(r):
        nonlocal new_shards, new_bytes
        if r.request.resource_type == "document" or r.url.endswith(
                (".css", ".js", ".woff2")):
            n = size_of(r)
            page_bytes[classify(r.url)] = page_bytes.get(classify(r.url), 0) + n
            if r.url.endswith(".woff2") and r.url not in seen:
                seen.add(r.url)
                new_shards += 1
                new_bytes += n

    page.on("response", on_resp)
    page.goto(url, wait_until="networkidle")
    page.remove_listener("response", on_resp)
    return page_bytes, new_shards, new_bytes


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    fonts_css = SITE / "public/fonts/fonts.css"
    httpd = serve(str(SITE / "dist"))
    base = "http://127.0.0.1:%d" % PORT
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME)
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            seen = set()

            # A. 冷缓存:文章页(内页最重)
            cold, _, _ = fetch_bytes(pg, base + "/posts/hello-nanmu-blog/", seen)
            total = sum(cold.values())
            print("A 冷缓存 /posts/hello-nanmu-blog/ 分类字节:")
            for k in ("html", "css", "js", "woff2", "other"):
                if k in cold:
                    print("   %-6s %8d B" % (k, cold[k]))
            print("   合计   %8d B (%.1f KB)" % (total, total / 1024))

            # B. 跨页面新增分片(同 context 已暖)
            for path in ("/posts/", "/digest/", "/about/"):
                _, ns, nb = fetch_bytes(pg, base + path, seen)
                print("B 暖访 %-9s 新增分片 %2d 个 / %6d B" % (path, ns, nb))
            pg.close()
            ctx.close()
            b.close()
    finally:
        httpd.shutdown()

    # C. fonts.css 磁盘体积
    if fonts_css.exists():
        raw = fonts_css.read_bytes()
        gz = gzip.compress(raw)
        print("C fonts.css 原始 %d B,gzip %d B" % (len(raw), len(gz)))
    else:
        print("C fonts.css 不存在")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
