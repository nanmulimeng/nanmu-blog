# -*- coding: utf-8 -*-
"""poster 中性主视觉拍摄工具(批次 C 资产轮,入库可复跑)。

复现流程承 R6 ASSETS.md 的 capture 链,渲染源为生产 public/3d/scene6.js
(内容同源契约,与运行时同一份纹理代码);数据来自
scripts/poster-capture.html 的中性栏目表达(不含被撤文章内容)。

产物:public/3d/poster-stack-{light,dark}.png(1440×850,昼/夜各一张)。
发布约束:单张 ≤450KiB(E2 预算口径,measure_budget.py 复测)。

用法(在 site/ 下):python -I scripts/poster_capture.py
"""
import http.server
import os
import shutil
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_browser import find_chrome  # noqa: E402 同目录脚本(-I 不自动加)

SITE = Path(__file__).resolve().parents[1]          # site/
SRC3D = SITE / "public" / "3d"
OUT = SRC3D
PORT = 8973
VIEWPORT = {"width": 1440, "height": 850}
SETTLE_MS = 3900      # 入场 2.8s + 主题插值余量(ASSETS.md 口径)


def serve(root, port):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(root), **k)

        def log_message(self, *a):
            pass
    class TS(socketserver.ThreadingTCPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            pass
    socketserver.TCPServer.allow_reuse_address = True
    httpd = TS(("127.0.0.1", port), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def link_fonts(tmp):
    """临时目录经 junction/符号链接引用生产字体目录(不复制几十 MiB
    分片);先例同 verify_digest_states.py 的 node_modules 链接。"""
    dst = tmp / "fonts"
    try:
        import _winapi
        _winapi.CreateJunction(str(SITE / "public" / "fonts"), str(dst))
    except (ImportError, OSError):
        os.symlink(str(SITE / "public" / "fonts"), str(dst))
    return dst


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="nanmu-poster-"))
    httpd = None
    linked = False
    try:
        # 拼装:生产场景 JS + 拍摄页;fonts 链接进临时根(css 相对路径成立)
        d3 = tmp / "3d"
        d3.mkdir(parents=True)
        for f in ("scene6.js", "three.module.min.js", "three.core.min.js"):
            shutil.copy2(SRC3D / f, d3 / f)
        shutil.copy2(SITE / "scripts" / "poster-capture.html", d3 / "poster-capture.html")
        link_fonts(tmp)
        linked = True

        httpd = serve(tmp, PORT)
        base = "http://127.0.0.1:%d/3d/poster-capture.html" % PORT
        with sync_playwright() as p:
            launch = ({"executable_path": find_chrome()}
                      if find_chrome() else {})
            b = p.chromium.launch(**launch)
            ctx = b.new_context(viewport=VIEWPORT,
                                device_scale_factor=1)
            errs = []
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errs.append(str(e)))
            for theme, name in ((None, "light"), ("dark", "dark")):
                url = base if theme is None else base + "?theme=" + theme
                pg.goto(url, wait_until="domcontentloaded")
                ok = pg.evaluate(
                    "() => new Promise(r => { const t0 = Date.now();"
                    " (function w(){ window.__captureReady"
                    " ? r(true) : Date.now() - t0 > 30000 ? r(false)"
                    " : setTimeout(w, 200); })(); })")
                if not ok:
                    print("[capture] %s: __captureReady 30s 超时,中止" % name)
                    return 1
                pg.wait_for_timeout(SETTLE_MS)
                out = OUT / ("poster-stack-%s.png" % name)
                pg.locator("#scene").screenshot(path=str(out))
                print("[capture] %s => %s (%.1f KiB)"
                      % (name, out.name, out.stat().st_size / 1024))
            if errs:
                print("[capture] 页面错误:%s" % errs[:3])
                return 1
            pg.close()
            ctx.close()
            b.close()
    finally:
        if httpd:
            httpd.shutdown()
        if linked:
            j = tmp / "fonts"
            try:
                os.rmdir(j)          # Windows junction:只删链接本身
            except OSError:
                j.unlink(missing_ok=True)
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
