# -*- coding: utf-8 -*-
"""预览隔离探针(工作台设计收口轮,2026-10-20)。

验证 DESIGN.md §4.3 预览隔离契约的机制可行性(设计验证,不是正式
工作台实现):响应头 CSP sandbox 使预览文档在**任何加载入口**
(管理页内嵌 iframe / 地址栏直开 / 新标签页)都进入 opaque origin,
活动内容发不出带会话的请求;管理 API 身份/CSRF 校验独立成立;
未登录与登录失效资源全拒;真实排版与分片字体可加载。

边界:临时服务+临时内容,无真实账号与凭据(PROBE_PASSWORD 是探针
占位符,不是任何真实口令),不连接生产/服务器;只读仓库
site/public/fonts 的字体文件做加载验证。

用法:python -I docs/design/2026-10-20-writing-workbench/probe_preview_isolation.py
(需要 site 的 Playwright 环境;Chromium 定位复用 site/scripts/verify_browser.find_chrome)
"""
import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "site" / "scripts"))
from verify_browser import find_chrome  # noqa: E402 跨目录复用(-I 不自动加)

PORT = 8983
PROBE_PASSWORD = "probe-placeholder"     # 探针占位符,非任何真实凭据
SESSIONS = set()                          # 活跃会话(内存)
RESULTS = []

FONTS = REPO / "site" / "public" / "fonts"

ADMIN_HTML = """<!doctype html><meta charset="utf-8">
<title>workbench-admin(probe)</title>
<style>body{font-family:serif;padding:16px}</style>
<p id="top-status">pending</p>
<iframe id="pv" sandbox="allow-scripts allow-popups"
        src="/preview/p1/index.html" style="width:640px;height:520px"></iframe>
<script>
  fetch('/api/drafts').then(r => r.status).then(s => {
    document.getElementById('top-status').textContent = 'top-fetch:' + s;
  });
</script>"""

PREVIEW_HTML = """<!doctype html><meta charset="utf-8">
<title>probe-loading</title>
<link rel="stylesheet" href="/preview/p1/fonts/fonts.css">
<style>
  body{font-family:'Noto Serif SC',serif;max-width:560px;margin:24px auto;
       padding:0 16px;line-height:1.9}
  h1{font-weight:900} blockquote{border-left:3px solid #B5432F;margin:0;
       padding-left:12px;color:#555}
</style>
<h1>校对样文——隔离探针</h1>
<p>这一段普通排版文字用于确认预览保留真实排版与字体加载:明暗主题
的样式部分、站内链接导航与文章配图都在首版保留范围内。</p>
<blockquote>引用块:不为复现全部装饰效果而放宽隔离。</blockquote>
<ul><li>列表项一</li><li>列表项二</li></ul>
<p><a href="/preview/p1/index.html">站内链接(前缀改写后留在预览命名空间)</a></p>
<script>
  (async () => {
    const out = {};
    try { const r = await fetch('/api/drafts'); out.api = r.status; }
    catch (e) { out.api = 'ERR:' + e.name; }
    try { out.cookie = document.cookie.length; }
    catch (e) { out.cookie = 'ERR:' + e.name; }
    try { localStorage.setItem('x', '1'); out.ls = 'writable'; }
    catch (e) { out.ls = 'ERR:' + e.name; }
    try { void window.top.location.href; out.top = 'self-or-readable'; }
    catch (e) { out.top = 'ERR:' + e.name; }
    document.title = JSON.stringify(out);
  })();
</script>"""


def check(label, ok, detail=""):
    RESULTS.append((label, ok))
    print("[%s] %s => %s" % (label, detail, "PASS" if ok else "FAIL"))


class H(http.server.BaseHTTPRequestHandler):
    def _send(self, code, body=b"", ctype="text/html; charset=utf-8", extra=()):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _sess(self):
        return ("sid=probe-session" in (self.headers.get("Cookie") or "")
                and "probe-session" in SESSIONS)   # 查会话表,非仅 cookie

    def _font_file(self, rest):
        # 只读映射 /preview/p1/fonts/<rest> -> site/public/fonts/<rest>
        target = (FONTS / rest).resolve()
        if (str(target).startswith(str(FONTS.resolve()) + "\\")
                and target.is_file()):
            return target
        return None

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/api/drafts":
            if not self._sess():
                return self._send(401, b'{"error":"no session"}',
                                  "application/json")
            return self._send(200, b'{"drafts": [{"slug": "probe-draft"}]}',
                              "application/json")
        if not self._sess():
            return self._send(401)
        if p == "/admin.html":
            return self._send(200, ADMIN_HTML.encode("utf-8"))
        if p == "/preview/p1/index.html":
            return self._send(
                200, PREVIEW_HTML.encode("utf-8"), extra=[
                    ("Content-Security-Policy",
                     "sandbox allow-scripts allow-popups"),
                    ("X-Robots-Tag", "noindex")])
        if p.startswith("/preview/p1/fonts/"):
            f = self._font_file(p[len("/preview/p1/fonts/"):])
            if f is None:
                return self._send(404)
            ctype = ("font/woff2" if f.suffix == ".woff2"
                     else "text/css; charset=utf-8")
            return self._send(200, f.read_bytes(), ctype)
        return self._send(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8", "replace")
        p = self.path.split("?")[0]
        if p == "/login":
            if "pw=" + PROBE_PASSWORD in body:
                SESSIONS.add("probe-session")
                return self._send(
                    200, b"ok", extra=[(
                        "Set-Cookie",
                        "sid=probe-session; HttpOnly; SameSite=Strict")])
            return self._send(401)
        if not self._sess():
            return self._send(401, b'{"error":"no session"}',
                              "application/json")
        origin = self.headers.get("Origin") or ""
        allowed = "http://127.0.0.1:%d" % PORT
        if p == "/api/drafts/delete":
            if origin != allowed:      # CSRF:来源校验独立于会话成立
                return self._send(403, b'{"error":"bad origin"}',
                                  "application/json")
            return self._send(200, b'{"deleted": "probe-draft"}',
                              "application/json")
        if p == "/api/session/expire":
            SESSIONS.discard("probe-session")
            return self._send(200, b"expired")
        return self._send(404)

    def log_message(self, *a):
        pass


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % PORT
    try:
        with sync_playwright() as pw:
            launch = ({"executable_path": find_chrome()}
                      if find_chrome() else {})
            b = pw.chromium.launch(**launch)

            # 1. 未登录:HTML/CSS/字体三个入口全部 401
            anon = b.new_context()
            r1 = [anon.request.get(base + u).status for u in (
                "/preview/p1/index.html",
                "/preview/p1/fonts/fonts.css",
                "/preview/p1/fonts/shards/noto-serif-sc-400-000.woff2")]
            check("probe/anon-401", r1 == [401, 401, 401], str(r1))
            anon.close()

            # 登录后的作者会话(APIRequestContext 与页面共享 cookie)
            ctx = b.new_context()
            pg = ctx.new_page()
            lr = ctx.request.post(
                base + "/login", form={"pw": PROBE_PASSWORD})
            if lr.status != 200:
                check("probe/login", False, "status=%d" % lr.status)
                raise SystemExit(1)

            # 2. 管理页顶层同源请求 200(对照:隔离不是把 API 关死)
            pg.goto(base + "/admin.html", wait_until="domcontentloaded")
            pg.wait_for_function(
                "document.getElementById('top-status')"
                ".textContent === 'top-fetch:200'", timeout=8000)
            check("probe/admin-top-api", True, "top fetch=200")

            # 3. 内嵌 iframe:活动内容不可达管理面 + 降级如实。
            #    实测:opaque origin 的 fetch 属跨源请求,被 CORS 层
            #    直接拦截(fetch 抛 TypeError,响应不可读)——比
            #    「401 不带会话」更强的不可达;localStorage/cookie
            #    抛 SecurityError,window.top 读取被拒。
            pv = next(f for f in pg.frames if "preview/p1/index.html" in f.url)
            pv.wait_for_function("document.title.startsWith('{')",
                                 timeout=8000)
            title = pv.evaluate("document.title")
            st = json.loads(title)
            check("probe/iframe-active",
                  st["api"] == "ERR:TypeError"
                  and st["ls"] == "ERR:SecurityError"
                  and st["cookie"] == "ERR:SecurityError"
                  and st["top"] == "ERR:SecurityError",
                  "api=%s ls=%s cookie=%s top=%s"
                  % (st["api"], st["ls"], st["cookie"], st["top"]))

            # 4. 地址栏直开(同会话新标签页):CSP 头同样生效。
            #    直开时 window.top==window,读自身 location 合法,不断言 top。
            pg2 = ctx.new_page()
            pg2.goto(base + "/preview/p1/index.html",
                     wait_until="domcontentloaded")
            pg2.wait_for_function(
                "document.title.startsWith('{')", timeout=8000)
            st2 = json.loads(pg2.title())
            check("probe/direct-open",
                  st2["api"] == "ERR:TypeError"
                  and st2["ls"] == "ERR:SecurityError",
                  "api=%s ls=%s top=%s(直开=top==self,合法)"
                  % (st2["api"], st2["ls"], st2["top"]))

            # 5. 真实排版+分片字体加载(直开页,resolve 后 check)
            pg2.evaluate("document.fonts.ready.then(() => 1)")
            pg2.wait_for_function(
                "document.fonts.status === 'loaded'", timeout=15000)
            font_ok = pg2.evaluate(
                "document.fonts.check(\"400 16px 'Noto Serif SC'\","
                " '这一段普通排版文字')")
            text_ok = pg2.inner_text("h1").strip() == "校对样文——隔离探针"
            check("probe/typography", bool(font_ok) and text_ok,
                  "font=%s h1=%s" % (font_ok, text_ok))

            # 6. CSRF:伪造 Origin 的管理写被独立拒绝(不靠 opaque)
            r2 = ctx.request.post(
                base + "/api/drafts/delete", headers={
                    "Origin": "https://evil.example",
                    "X-Requested-With": "probe"})
            r3 = ctx.request.post(base + "/api/drafts/delete",
                                  headers={"Origin": base})
            check("probe/csrf-origin", r2.status == 403 and r3.status == 200,
                  "evil=%d same=%d" % (r2.status, r3.status))

            # 7. 登录失效:同会话再请求预览资源 -> 401
            ctx.request.post(base + "/api/session/expire",
                             headers={"Origin": base})
            r5 = ctx.request.get(base + "/preview/p1/index.html")
            check("probe/session-expired", r5.status == 401,
                  "after expire=%d" % r5.status)

            pg.close(); pg2.close(); ctx.close(); b.close()
    finally:
        httpd.shutdown()

    fails = [l for l, ok in RESULTS if not ok]
    print("\n== %d/%d PASS ==" % (len(RESULTS) - len(fails), len(RESULTS)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
