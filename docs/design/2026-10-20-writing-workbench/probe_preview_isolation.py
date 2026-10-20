# -*- coding: utf-8 -*-
"""预览隔离与资源加载探针 v2(工作台设计收口轮,2026-10-20)。

对 v1 的勘误:v1 的 typography 断言无效——实测预览 HTML 200 但
fonts.css 401(CSP sandbox 使文档进入 opaque origin,其子资源请求
不带会话 cookie)、document.fonts 为空、fonts.check 对目标字体与
不存在的字体都返回 true(无区分度,不可作证据)。v1 报告的
「7/7 PASS」中字体项不成立;本版把这一组直接纳入失败判据。

验证对象(DESIGN.md §4.3,设计验证非正式实现):
- 预览=响应头 CSP sandbox(**无 allow-scripts**,静态校对预览:
  作者活动脚本与增强脚本一律不执行),任何加载入口一致;
- 预览资源(CSS/字体分片/图片)经短期 token 加载:token 由服务端
  在返回预览 HTML 时签发、绑定会话、30 分钟过期;子资源 URL 带
  token,CSS 内容内的分片 URL 由服务端改写补 token。会话失效
  →token 同步失效→资源重请求按契约拒绝(不承诺抹除已下载内容);
- 安全验证以**服务端请求记录**为准(到达/方法/Origin/会话校验
  结果/返回状态/数据是否被修改),浏览器行为只作旁证:
  预览内活动脚本被 CSP 阻止的判据=服务端记录零 /api 请求到达,
  不以「fetch 抛 TypeError」当作「请求不可达服务端」的证据。

三阶段(先证明探针能识别当前失败,再验证方案,再反向自检):
- RED  (--phase red): cookie-only 模式(资源仅认会话 cookie,
  模拟审计复现的当前失败)→ 资源组判据必须 FAIL;
- GREEN(--phase green): token 方案 → 三组(资源/安全/合法对照)
  判据通过;
- BLOCK(--phase block): token 方案但 fonts.css 恒 401 → 资源组
  判据必须 FAIL(阻断资源时验收不得静默以系统字体算通过)。

边界:临时服务+临时内容;PROBE_PASSWORD 是探针占位符,非任何真实
凭据;不连生产/服务器;只读 site/public/fonts 的字体文件。

用法(在 site/ 目录,复用其 Playwright 环境):
python -I ../docs/design/2026-10-20-writing-workbench/probe_preview_isolation.py
可选 --phase red|green|block(默认三阶段连跑)。
"""
import argparse
import base64
import json
import re
import secrets
import socketserver
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "site" / "scripts"))
from verify_browser import find_chrome  # noqa: E402 跨目录复用(-I 不自动加)

PORT = 8993
PROBE_PASSWORD = "probe-placeholder"     # 探针占位符,非任何真实凭据
SESSIONS = set()                          # 活跃会话(内存)
TOKENS = {}                               # token -> {"sid":..., "exp":...}
TOKEN_TTL = 1800                          # 30 分钟
REQLOG = []                               # 服务端请求记录(最小事实)
PREVIEWS = {"p1", "p2"}                   # 存活预览(内存;删除=discard)
DRAFTS = {                                # 内存写目标:非法请求后状态必须不变
    "probe-draft": {"title": "校对样文"},
    "probe-draft-2": {"title": "对照草稿"},
}
MODE = "token"          # 'cookie-only'=模拟当前失败;'token'=方案
BLOCK_CSS = False       # True=fonts.css 恒 401(反向自检)
FONTS = REPO / "site" / "public" / "fonts"
PNG_1PX = base64.b64decode(  # 1x1 透明 PNG(预览配图加载验证)
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    b"YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

ADMIN_HTML = """<!doctype html><meta charset="utf-8">
<title>workbench-admin(probe)</title>
<p id="top-status">pending</p>
<!-- iframe 属性 sandbox="" 仅纵深;真正的隔离由文档响应头 CSP 提供 -->
<iframe id="pv" sandbox="" src="/preview/p1/index.html"
        style="width:640px;height:420px"></iframe>
<script>
  fetch('/api/drafts').then(r => r.status).then(s => {
    document.getElementById('top-status').textContent = 'top-fetch:' + s;
  });
</script>"""

PREVIEW_HTML = """<!doctype html><meta charset="utf-8">
<title>校对样文——静态预览探针</title>
<link rel="stylesheet" href="/preview/p1/fonts/fonts.css?t={TOKEN}">
<img src="/preview/p1/img/fig.png?t={TOKEN}" alt="配图" width="8" height="8">
<style>
  body{font-family:'Noto Serif SC',serif;max-width:560px;margin:24px auto;
       padding:0 16px;line-height:1.9}
  h1{font-weight:900}
</style>
<h1>校对样文——静态预览探针</h1>
<p>这一段普通排版文字用于确认静态校对预览保留真实排版与字体加载:
自动挑题、摘要与配图在首版保留范围内。</p>
<h2 id="sec">锚点目标小节</h2>
<p>链接首版收敛示例(构建后改写形态):站内链接
<a data-wb-target="/posts/example/">《旧文标题》</a>、外部链接
<a data-wb-target="https://example.com/ref">外部参考</a>
——保留文字与目标信息、不可导航;页内锚点
<a href="#sec">回到小节</a>(同文档滚动,保留)。</p>
<!-- 作者活动内容(探针故意放置):CSP sandbox 无 allow-scripts
     应阻止其执行——判据在服务端请求记录,不在页面内 -->
<script>
  window.__probe_marker = 'ran';
  fetch('/api/drafts').then(r => { window.__probe_marker = 'api:' + r.status; });
</script>"""


def slog(method, path, origin, auth, status, mutated=False):
    """服务端请求记录:探针断言以此为准确事实来源。"""
    REQLOG.append({"m": method, "path": path.split("?")[0],
                   "origin": origin, "auth": auth, "status": status,
                   "mutated": mutated})


def api_log():
    return [e for e in REQLOG if e["path"].startswith("/api")]


class H(BaseHTTPRequestHandler):
    def _send(self, code, body=b"", ctype="text/html; charset=utf-8",
              extra=()):
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

    def _token_ok(self, pid, kind):
        m = re.search(r"[?&]t=([0-9a-f]+)", self.path)
        if not m:
            return False
        rec = TOKENS.get(m.group(1))
        # 有效=未过期 且 绑定会话仍活跃 且 预览仍存活
        # 且 凭证所属预览=请求的预览 且 资源类别在允许范围内
        return bool(rec and rec["exp"] > time.time()
                    and rec["sid"] in SESSIONS
                    and rec["pid"] == pid and pid in PREVIEWS
                    and kind in rec["kinds"])

    def _font_file(self, rest):
        # 只读映射 /preview/p1/fonts/<rest> -> site/public/fonts/<rest>
        target = (FONTS / rest).resolve()
        if (str(target).startswith(str(FONTS.resolve()) + "\\")
                and target.is_file()):
            return target
        return None

    def do_GET(self):
        p = self.path.split("?")[0]
        origin = self.headers.get("Origin")
        mres = re.match(r"^/preview/(p[12])/(fonts|img)/(.+)$", p)
        pid = mres.group(1) if mres else None
        if p == "/api/drafts":
            ok = self._sess()
            slog("GET", p, origin, "session" if ok else "none",
                 200 if ok else 401)
            if not ok:
                return self._send(401, b'{"error":"no session"}',
                                  "application/json")
            return self._send(200, json.dumps(
                {"drafts": sorted(DRAFTS)}).encode(), "application/json")
        if pid and p == "/preview/%s/fonts/fonts.css" % pid:
            # 资源只走 token 校验(opaque origin 子资源不带 cookie,
            # 全局会话检查会先把它拒掉——这正是 v1 失败的机制)
            if MODE == "cookie-only" or BLOCK_CSS:
                # cookie-only=模拟当前失败:opaque 子资源不带 cookie
                slog("GET", p, origin, "none", 401)
                return self._send(401)
            if pid not in PREVIEWS:
                slog("GET", p, origin, "preview-gone", 410)
                return self._send(410)
            if not self._token_ok(pid, "css"):
                slog("GET", p, origin, "bad-or-expired-token", 401)
                return self._send(401)
            slog("GET", p, origin, "token", 200)
            tok = re.search(r"[?&]t=([0-9a-f]+)", self.path).group(1)
            css = (FONTS / "fonts.css").read_text("utf-8")
            # 服务端改写:CSS 内分片 URL 补同 token
            css = re.sub(r"url\((['\"]?)(shards/[^'\")]+)",
                         r"url(\1\2?t=" + tok, css)
            # 探针标记:只可能来自这份外部 CSS(内联样式给不出),
            # 用于判据「外部样式确实应用」——401 时变量为空
            css += "\nbody{--probe-ext-css:applied}"
            return self._send(200, css.encode("utf-8"),
                              "text/css; charset=utf-8")
        if pid and p.startswith("/preview/%s/fonts/shards/" % pid):
            if MODE == "cookie-only":
                slog("GET", p, origin, "none", 401)
                return self._send(401)
            if pid not in PREVIEWS:
                slog("GET", p, origin, "preview-gone", 410)
                return self._send(410)
            if not self._token_ok(pid, "font"):
                slog("GET", p, origin, "bad-or-expired-token", 401)
                return self._send(401)
            f = self._font_file(p[len("/preview/%s/fonts/" % pid):])
            if f is None:
                slog("GET", p, origin, "token", 404)
                return self._send(404)
            slog("GET", p, origin, "token", 200)
            # 字体加载走 CORS 模式:opaque origin 文档视为跨源,
            # 响应须带 ACAO 才能被字体层接受(诊断实验证实:无此头
            # 时请求到达且 200,但 FontFace 停留 unloaded)。
            # ACAO:* 只作用于公开字体文件,不涉及草稿内容。
            return self._send(200, f.read_bytes(), "font/woff2", extra=[
                ("Access-Control-Allow-Origin", "*")])
        if pid and p == "/preview/%s/img/fig.png" % pid:
            if MODE == "cookie-only":
                slog("GET", p, origin, "none", 401)
                return self._send(401)
            if pid not in PREVIEWS:
                slog("GET", p, origin, "preview-gone", 410)
                return self._send(410)
            if not self._token_ok(pid, "img"):
                slog("GET", p, origin, "bad-or-expired-token", 401)
                return self._send(401)
            slog("GET", p, origin, "token", 200)
            return self._send(200, PNG_1PX, "image/png")
        if not self._sess():
            slog("GET", p, origin, "none", 401)
            return self._send(401)
        if p == "/admin.html":
            slog("GET", p, origin, "session", 200)
            return self._send(200, ADMIN_HTML.encode("utf-8"))
        if p in ("/preview/p1/index.html", "/preview/p2/index.html"):
            hpid = p.split("/")[2]
            slog("GET", p, origin, "session", 200)
            tok = secrets.token_hex(8)
            # 最小记录范围:所属会话/所属预览/有效期/允许类别
            # (bearer 凭证,子资源请求不要求登录 cookie)
            TOKENS[tok] = {"sid": "probe-session", "pid": hpid,
                           "exp": time.time() + TOKEN_TTL,
                           "kinds": ("css", "font", "img")}
            body = PREVIEW_HTML.replace("{TOKEN}", tok).encode("utf-8")
            return self._send(200, body, extra=[
                ("Content-Security-Policy", "sandbox"),  # 无 allow-scripts
                ("Referrer-Policy", "no-referrer"),      # token 不随 Referer 外泄
                ("X-Robots-Tag", "noindex")])
        slog("GET", p, origin, "session", 404)
        return self._send(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8", "replace")
        p = self.path.split("?")[0]
        origin = self.headers.get("Origin")
        allowed = "http://127.0.0.1:%d" % PORT
        if p == "/login":
            ok = "pw=" + PROBE_PASSWORD in body
            slog("POST", p, origin, "form", 200 if ok else 401)
            if not ok:
                return self._send(401)
            SESSIONS.add("probe-session")
            return self._send(200, b"ok", extra=[(
                "Set-Cookie",
                "sid=probe-session; HttpOnly; SameSite=Strict")])
        if p == "/api/session/expire":
            SESSIONS.discard("probe-session")
            slog("POST", p, origin, "explicit-expire", 200)
            return self._send(200, b"expired")
        if p == "/api/drafts/delete":
            # 写接口三层校验,各自独立成立;顺序=会话→Origin→自定义头
            if not self._sess():
                slog("POST", p, origin, "none", 401)
                return self._send(401, b'{"error":"no session"}',
                                  "application/json")
            if origin != allowed:      # 非法或缺失(null)Origin 都拒
                slog("POST", p, origin, "session", 403)
                return self._send(403, b'{"error":"bad origin"}',
                                  "application/json")
            if self.headers.get("X-Requested-With") != "XMLHttpRequest":
                slog("POST", p, origin, "session", 403)
                return self._send(403, b'{"error":"bad header"}',
                                  "application/json")
            slug = "probe-draft-2"     # 探针固定删除目标(真删,可查状态)
            mutated = DRAFTS.pop(slug, None) is not None
            slog("POST", p, origin, "session", 200, mutated=mutated)
            return self._send(200, json.dumps(
                {"remaining": sorted(DRAFTS)}).encode(), "application/json")
        slog("POST", p, origin, "session", 404)
        return self._send(404)

    def log_message(self, *a):
        pass


# ---------------------------------------------------------------- 断言


def check(res, group, label, ok, detail=""):
    res.append((group, label, ok, detail))
    print("[%s][%s] %s => %s" % (group, label, detail,
                                 "PASS" if ok else "FAIL"))


def netmap(pg):
    """网络层记录:url -> 最终响应状态(判据以响应状态为准,
    不以『请求发生过』代替)。"""
    m = {}

    def on_resp(r):
        m[r.url] = r.status
    pg.on("response", on_resp)
    return m


def run_browser(res):
    with sync_playwright() as pw:
        launch = ({"executable_path": find_chrome()}
                  if find_chrome() else {})
        b = pw.chromium.launch(**launch)

        # ---- 组 1 前置:未登录三入口(安全组 S1 也用这组数字)----
        anon = b.new_context()
        r_anon = [anon.request.get(
            "http://127.0.0.1:%d%s" % (PORT, u)).status for u in (
            "/preview/p1/index.html",
            "/preview/p1/fonts/fonts.css",
            "/preview/p1/fonts/shards/noto-serif-sc-400-000.woff2",
            "/preview/p1/img/fig.png")]
        check(res, "S", "anon-401-html-css-font-img",
              r_anon == [401, 401, 401, 401], str(r_anon))
        anon.close()

        # ---- 登录后的作者会话 ----
        ctx = b.new_context()
        lr = ctx.request.post("http://127.0.0.1:%d/login" % PORT,
                              form={"pw": PROBE_PASSWORD})
        if lr.status != 200:
            check(res, "L", "login", False, "status=%d" % lr.status)
            raise SystemExit(1)

        # ---- 组 1:资源加载(直开预览页,静态文档)----
        pg2 = ctx.new_page()
        nm = netmap(pg2)
        resp = pg2.goto("http://127.0.0.1:%d/preview/p1/index.html" % PORT)
        check(res, "R", "r1-preview-html-200", resp.status == 200,
              "html=%d" % resp.status)
        csp = (resp.headers or {}).get("content-security-policy", "")
        check(res, "R", "r1b-csp-no-scripts",
              csp == "sandbox", repr(csp))
        pg2.wait_for_timeout(2500)      # 等子资源完成(静态页无脚本可等)

        css_st = next((v for k, v in nm.items()
                       if "fonts.css" in k), None)
        check(res, "R", "r2-fonts-css-200", css_st == 200,
              "fonts.css=%s" % css_st)
        woff_ok = sorted(k.rsplit("/", 1)[-1].split("?")[0]
                         for k, v in nm.items()
                         if ".woff2" in k and v == 200)
        check(res, "R", "r3-woff2-shard-200", len(woff_ok) >= 1,
              "分片200×%d %s" % (len(woff_ok), woff_ok[:3]))
        img_st = next((v for k, v in nm.items() if "fig.png" in k), None)
        check(res, "R", "r3b-img-200", img_st == 200, "img=%s" % img_st)

        # FontFaceSet:目标族存在且 loaded(字体真实可用的判据——
        # 网络层 200 只是必要条件,CORS 拒绝的响应同样显示 200,
        # 实测确认以 FontFace loaded 为准)。
        # 注:sandbox(无 allow-scripts)文档里注入函数不能作原生
        # API 的回调(forEach 报 not runnable),数字索引也不存在,
        # 用 for-of 迭代;跨源 stylesheet 的 cssRules 不可读(预期
        # 行为,不作为判据)。
        ff = pg2.evaluate("""() => {
            const out = [];
            try {
                for (const f of document.fonts) {
                    out.push(f.family + '|' + f.weight + '|' + f.status);
                }
            } catch (e) { out.push('ITER-ERR:' + e.name); }
            return {faces: out, status: document.fonts.status}; }""")
        loaded = [x for x in ff["faces"] if x.startswith("Noto Serif SC")
                  and x.endswith("|loaded")]
        check(res, "R", "r4-fontface-loaded",
              len(loaded) >= 1 and ff["status"] == "loaded",
              "loaded=%d/%s;fonts.status=%s"
              % (len(loaded), ff["faces"][:4], ff["status"]))

        # fonts.check 区分度自检(用户审计结论的实证):对不存在的
        # 字体族也返回 true → 该信号在本环境无区分度,排除出证据链。
        # 此判据 PASS 的含义=「正确识别 check 不可用并如实记录」,
        # 不是「字体可用」的证据。
        chk_real = pg2.evaluate(
            "document.fonts.check(\"400 16px 'Noto Serif SC'\", '排版文字')")
        chk_fake = pg2.evaluate(
            "document.fonts.check(\"400 16px 'Nope Serif XX'\", '排版文字')")
        check(res, "R", "r5-check-no-discriminating-power-recorded",
              chk_fake is True,
              "real=%s fake=%s(fake 亦为 true → check 无区分度,"
              "已排除出证据链,字体可用性以 r4 为准)"
              % (chk_real, chk_fake))

        # 外部样式生效:只能由外部 CSS 设置的变量实际生效
        # (页面内联样式给不出;fonts.css 401 时变量为空→FAIL)
        ext = pg2.evaluate(
            "getComputedStyle(document.body)"
            ".getPropertyValue('--probe-ext-css').trim()")
        mw = pg2.evaluate("getComputedStyle(document.body).maxWidth")
        check(res, "R", "r6-external-css-applied", ext == "applied",
              "--probe-ext-css=%r(内联可给的 maxWidth=%s 仅作参考)"
              % (ext, mw))
        txt = pg2.inner_text("h1").strip()
        check(res, "R", "r6b-sample-text", "校对样文" in txt, txt)

        # ---- 组 2:S3 预览内活动脚本被 CSP 阻止(服务端记录为准)----
        n_api = len(api_log())
        marker = pg2.evaluate("typeof window.__probe_marker")
        check(res, "S", "s3-preview-script-blocked-server-side",
              n_api == 0 and marker == "undefined",
              "api_hits=%d marker=%s(CSP 无 allow-scripts:脚本未执行,"
              "请求未到达服务端)" % (n_api, marker))

        # ---- 内嵌入口:同一文档,隔离一致 ----
        pg = ctx.new_page()
        pg.goto("http://127.0.0.1:%d/admin.html" % PORT)
        pg.wait_for_function(
            "document.getElementById('top-status').textContent"
            " === 'top-fetch:200'", timeout=8000)
        check(res, "L", "l1-admin-top-fetch-200", True,
              "顶层同源 fetch=200(服务端记录见 REQLOG)")
        fr = next(f for f in pg.frames
                  if "preview/p1/index.html" in f.url)
        fr.wait_for_timeout(800)
        fr_txt = fr.inner_text("h1")
        n_api2 = len([e for e in api_log()
                      if e["path"] == "/api/drafts"])
        check(res, "S", "s3b-iframe-entry-same-doc",
              "校对样文" in fr_txt and n_api2 == 1,
              "iframe 文档加载=%s;/api/drafts 到达数=%d(仅顶层那 1 次)"
              % ("校对样文" in fr_txt, n_api2))

        # ---- 组 3:合法写对照(真删,数据状态为准)----
        before = json.dumps(sorted(DRAFTS), ensure_ascii=False)
        rd = ctx.request.post(
            "http://127.0.0.1:%d/api/drafts/delete" % PORT,
            headers={"Origin": "http://127.0.0.1:%d" % PORT,
                     "X-Requested-With": "XMLHttpRequest"})
        after = json.dumps(sorted(DRAFTS), ensure_ascii=False)
        entry = api_log()[-1]
        check(res, "L", "l2-legal-delete-mutates",
              rd.status == 200 and before != after and entry["mutated"],
              "status=%d 数据变化=%s 服务端记录 mutated=%s"
              % (rd.status, before != after, entry["mutated"]))

        # ---- 组 2:S4 直连写 API 四路(服务端校验+数据不变)----
        snap = json.dumps(sorted(DRAFTS), ensure_ascii=False)
        base = "http://127.0.0.1:%d/api/drafts/delete" % PORT
        no_sess = b.new_context()                     # 无会话上下文
        c1 = no_sess.request.post(base, headers={
            "Origin": "http://127.0.0.1:%d" % PORT,
            "X-Requested-With": "XMLHttpRequest"})
        c2 = ctx.request.post(base, headers={
            "Origin": "https://evil.example",
            "X-Requested-With": "XMLHttpRequest"})
        c3 = ctx.request.post(base, headers={          # 不带 Origin(null)
            "X-Requested-With": "XMLHttpRequest"})
        c4 = ctx.request.post(base, headers={
            "Origin": "http://127.0.0.1:%d" % PORT})   # 缺自定义头
        no_sess.close()
        snap2 = json.dumps(sorted(DRAFTS), ensure_ascii=False)
        log4 = api_log()[-4:]
        check(res, "S", "s4-write-guard-4-ways",
              c1.status == 401 and c2.status == 403
              and c3.status == 403 and c4.status == 403
              and snap == snap2
              and not any(e["mutated"] for e in log4),
              "无会话=%d 伪造Origin=%d null-Origin=%d 缺XRW=%d;"
              "数据未变=%s;服务端记录=%s"
              % (c1.status, c2.status, c3.status, c4.status,
                 snap == snap2,
                 [(e["auth"], e["status"]) for e in log4]))

        # ---- 组 T:资源 token 边界(短期 bearer 资源凭证)----
        # 无会话上下文验证:token 是独立凭证,子资源不要求登录 cookie
        noku = b.new_context()
        base_u = "http://127.0.0.1:%d" % PORT

        def tget(u):
            return noku.request.get(base_u + u).status
        r_html = ctx.request.get(base_u + "/preview/p1/index.html")
        tokA = re.search(r"[?&]t=([0-9a-f]+)", r_html.text()).group(1)
        t1 = tget("/preview/p1/fonts/fonts.css?t=" + tokA)
        check(res, "T", "t1-token-loads-own-css", t1 == 200,
              "无 cookie 上下文+token=%d(bearer 凭证独立起作用)" % t1)
        t2 = tget("/preview/p2/fonts/fonts.css?t=" + tokA)
        check(res, "T", "t2-cross-preview-denied", t2 in (401, 403),
              "A 的 token 访问 B 预览资源=%d(须拒,token 绑定预览)"
              % t2)
        t3a = tget("/preview/p1/index.html?t=" + tokA)
        t3b = tget("/api/drafts?t=" + tokA)
        check(res, "T", "t3-token-not-for-html-api",
              t3a == 401 and t3b == 401,
              "HTML=%d API=%d(token 不替代会话;HTML 只走登录路径,"
              "管理 API 永不接受资源 token)" % (t3a, t3b))
        # 到期:可控时钟=直接修改临时记录,不实际等待 30 分钟
        TOKENS[tokA]["exp"] = time.time() - 1
        t4 = tget("/preview/p1/fonts/shards/"
                  "noto-serif-sc-400-000.woff2?t=" + tokA)
        check(res, "T", "t4-expiry-denied", t4 == 401,
              "到期后=%d(会话失效拒绝见 S2,此条只验凭证自身到期)"
              % t4)
        TOKENS[tokA]["exp"] = time.time() + TOKEN_TTL
        # 预览被删除:未过期 token 也不得继续访问
        PREVIEWS.discard("p1")
        t5 = tget("/preview/p1/fonts/fonts.css?t=" + tokA)
        check(res, "T", "t5-preview-deleted-denied", t5 in (401, 410),
              "预览删除后=%d(24h 保留期与 30min 凭证相互独立,"
              "预览没了凭证随之失效)" % t5)
        # 有效会话重开保留期内预览:获得新凭证(与旧凭证不同且可用)
        PREVIEWS.add("p1")
        r_html2 = ctx.request.get(base_u + "/preview/p1/index.html")
        m6 = re.search(r"[?&]t=([0-9a-f]+)", r_html2.text())
        tokB = m6.group(1) if m6 else ""
        t6 = tget("/preview/p1/fonts/fonts.css?t=" + tokB) if tokB else 0
        check(res, "T", "t6-reopen-issues-new-token",
              bool(tokB) and tokB != tokA and t6 == 200,
              "新凭证≠旧且可用=%s(token 值不入日志与交接)"
              % (bool(tokB) and tokB != tokA and t6 == 200))
        noku.close()

        # ---- 组 2:S2 会话失效:HTML/CSS/字体/图片重请求全拒 ----
        # 先取已签发 token 的资源 URL(expire 之前 HTML 可取),
        # 验证「会话失效 → token 连带失效」而非仅仅「无 token 拒绝」
        r_html = ctx.request.get(
            "http://127.0.0.1:%d/preview/p1/index.html" % PORT)
        m = re.search(r"[?&]t=([0-9a-f]+)", r_html.text())
        tok = m.group(1) if m else ""
        ctx.request.post("http://127.0.0.1:%d/api/session/expire" % PORT)
        r_exp = [ctx.request.get(
            "http://127.0.0.1:%d%s" % (PORT, u)).status for u in (
            "/preview/p1/index.html",
            "/preview/p1/fonts/fonts.css?t=" + tok,
            "/preview/p1/fonts/shards/noto-serif-sc-400-000.woff2?t=" + tok,
            "/preview/p1/img/fig.png?t=" + tok)]
        # css/woff2/img 用已签发 token——会话已失效,token 须连带失效
        check(res, "S", "s2-expired-session-resources-401",
              bool(tok) and r_exp == [401, 401, 401, 401],
              "token=%s expire后=%s(token 绑定会话,已下载内容不承诺远程抹除)"
              % (tok[:8] + "…" if tok else "无", r_exp))

        pg.close(); pg2.close(); ctx.close()

        # ---- 组 N:导航首版收敛(实际点击,不只查 href 字符串)----
        # 在独立上下文重开预览页(S2 已使会话失效,重登后点击)
        ctx3 = b.new_context()
        ctx3.request.post("http://127.0.0.1:%d/login" % PORT,
                          form={"pw": PROBE_PASSWORD})
        pg3 = ctx3.new_page()
        pg3.goto("http://127.0.0.1:%d/preview/p1/index.html" % PORT)
        pg3.wait_for_timeout(800)
        url_before = pg3.url
        req_loaded = len(REQLOG)
        # 实际点击改写后的站内/外部链接:零导航、零新资源请求
        pg3.click("a[data-wb-target='/posts/example/']")
        pg3.click("a[data-wb-target='https://example.com/ref']")
        pg3.wait_for_timeout(600)
        n_new = len([e for e in REQLOG[req_loaded:]
                     if e["path"].startswith("/preview")])
        check(res, "N", "n12-links-no-nav",
              pg3.url == url_before and n_new == 0,
              "url 不变=%s;/preview 新请求=%d(链接不可导航=点击后"
              "零跳转零请求,以服务端记录与页面 url 为准)"
              % (pg3.url == url_before, n_new))
        # 页内锚点:同文档滚动生效(校对需求内保留,不产生请求)
        req_before_anchor = len(REQLOG)
        pg3.click("a[href='#sec']")
        pg3.wait_for_timeout(400)
        h = pg3.evaluate("location.hash")
        n_anchor = len([e for e in REQLOG[req_before_anchor:]
                        if e["path"].startswith("/preview")])
        check(res, "N", "n3-anchor-same-doc",
              h == "#sec" and n_anchor == 0,
              "hash=%s;锚点新请求=%d(同文档滚动,非导航)"
              % (h, n_anchor))
        pg3.close(); ctx3.close()
        b.close()


def summary(res, phase, expect_pass):
    fails = [(g, l) for g, l, ok, _ in res if not ok]
    groups = {}
    for g, l, ok, d in res:
        groups.setdefault(g, [0, 0])
        groups[g][0 if ok else 1] += 1
    print("\n== %s: %d/%d PASS ==" % (phase, len(res) - len(fails), len(res)))
    for g, (ok_c, bad_c) in sorted(groups.items()):
        print("   组%s:%d 通过 / %d 失败" % (g, ok_c, bad_c))
    if expect_pass:
        return 0 if not fails else 1
    return 1 if fails else 0    # 期望 FAIL 的阶段:有失败=探针有区分度


def phase_setup(mode, block_css=False):
    global MODE, BLOCK_CSS, SESSIONS, TOKENS, REQLOG, DRAFTS
    MODE, BLOCK_CSS = mode, block_css
    SESSIONS = set()
    TOKENS = {}
    REQLOG = []
    DRAFTS = {"probe-draft": {"title": "校对样文"},
              "probe-draft-2": {"title": "对照草稿"}}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["red", "green", "block", "all"],
                    default="all")
    args = ap.parse_args()
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    rc = 0
    try:
        if args.phase in ("red", "all"):
            print("---- 阶段 RED:cookie-only(模拟审计复现的当前失败)----")
            phase_setup("cookie-only")
            res = []
            run_browser(res)
            rc |= summary(res, "RED", expect_pass=False)
        if args.phase in ("green", "all"):
            print("---- 阶段 GREEN:token 方案(静态预览+签名资源)----")
            phase_setup("token")
            res = []
            run_browser(res)
            rc |= summary(res, "GREEN", expect_pass=True)
        if args.phase in ("block", "all"):
            print("---- 阶段 BLOCK:token 方案但 fonts.css 恒 401(反向自检)----")
            phase_setup("token", block_css=True)
            res = []
            try:
                run_browser(res)
            except Exception as e:      # 反向阶段允许浏览器步骤报错,
                print("(block 阶段浏览器步骤异常,继续汇总:%s)"
                      % str(e)[:120])   # 只看资源组判据是否转红
            rc |= summary(res, "BLOCK", expect_pass=False)
    finally:
        httpd.shutdown()
    return rc


if __name__ == "__main__":
    sys.exit(main())
