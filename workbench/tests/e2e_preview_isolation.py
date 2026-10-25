# -*- coding: utf-8 -*-
"""批 2 浏览器级隔离验收(2026-10-25,DESIGN §4.3 在真实服务上)。

对象:正式实现(POST /api/preview 触发链+preview_build/rewriter/previews/
app 路由)+真实 Astro 构建产物(两篇哨兵草稿,含活动脚本样例)+
node src/server.js 真实进程。独立临时目录+占位口令,不连生产不碰本仓库。

覆盖:
- A0 触发链:登录→PUT 草稿→POST /api/preview→真实构建注册
- R1 未登录 HTML 401
- R2 哨兵可见+横幅+CSP=sandbox+noindex;字体链路 fonts.css 200→woff2 分片
  200+ACAO:*(DESIGN:网络 200 单独不足,但 CSP 页内 evaluate 由 CDP 注入,
  此处以响应头与分片全链 200 为网络层证据;fonts.check 无区分度不采用)
- R3 活动内容零执行:草稿含 <script>fetch('/api/pwn*')</script> 与 img onerror;
  判据=服务端请求记录零到达(DESIGN 定案)
- R4 实际点击站内/外部:url 不变+服务端零新 /preview 请求;R4b 页内锚点滚动
- R5 双预览各自哨兵互不串
- R6 登出:旧 token 子资源 401+HTML 401
- R7 未注册/已删预览 410
- BLOCK 阻断 fonts.css:字体判据必须 FAIL(验收区分度,反例 11)

用法(workbench/ 下):python -I tests/e2e_preview_isolation.py
退出码:0=全部符合预期;1=存在不符合预期。
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
WB = Path(__file__).resolve().parents[1]
REPO = WB.parent
PW_TEXT = "e2e-placeholder-password"
SENT_A = "sentinel-real-aaa-111"
SENT_B = "sentinel-real-bbb-222"
BASE_HDR = {"Content-Type": "application/json"}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_http(base, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(base + "/login", timeout=1)
            return True
        except Exception:
            time.sleep(0.2)
    return False


def req(base, method, path, body=None, headers=None):
    data = None
    h = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=300) as resp:
            return resp.status, resp.read(), {k.lower(): v for k, v in resp.headers.items()}, resp
    except urllib.error.HTTPError as e:
        return e.code, e.read(), {k.lower(): v for k, v in e.headers.items()}, e


import json  # noqa: E402


def draft_body(sent, tag):
    return (f"---\ntitle: 隔离验收{tag}\npubDate: 2026-10-25\ntags: []\ndraft: false\n---\n\n"
            f"正文哨兵 {sent}。\n\n"
            f"<script>fetch('/api/pwn{tag}');window.__pwned{tag}=true;</script>\n\n"
            f"<img src=\"/img/404-never.png\" onerror=\"fetch('/api/pwn-err{tag}')\" alt=\"x\">\n\n"
            f"[站内链接](/posts/other/) [外部链接](https://example.com/x) [锚点](#bottom)\n\n"
            f"<div id=\"bottom\">底部锚点</div>\n")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="wb-e2e-prev-"))
    previews_dir = tmp / "previews"
    drafts_dir = tmp / "drafts"
    bare = tmp / "mirror.git"
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log = tmp / "server.log"
    ok_all = []

    def check(name, ok, detail=""):
        ok_all.append((name, ok, detail))
        print(("PASS" if ok else "FAIL"), name, detail)

    try:
        subprocess.run(["git", "clone", "--bare", "-b", "workbench-batch2",
                        str(REPO), str(bare)], capture_output=True, check=True)
        env = {**os.environ, "PORT": str(port), "WB_DEV_PASSWORD": PW_TEXT,
               "WB_DRAFTS_DIR": str(drafts_dir), "WB_PREVIEWS_DIR": str(previews_dir),
               "WB_PREVIEW_REPO": str(bare), "WB_PREVIEW_BRANCH": "workbench-batch2",
               "WB_BASE_URL": base}
        srv = subprocess.Popen(["node", "src/server.js"], cwd=str(WB), env=env,
                               stdout=open(log, "w", encoding="utf-8"),
                               stderr=subprocess.STDOUT)
        assert wait_http(base), "服务未就绪"

        # ── A0 登录→存草稿→触发真实构建(两次,~35s) ──
        st, body, hdrs, _ = req(base, "POST", "/api/login", {"password": PW_TEXT})
        sc = hdrs.get("Set-Cookie") or hdrs.get("set-cookie") or ""
        cookie = re.search(r"(wb_session=[^;]+)", sc).group(1)
        csrf = {"cookie": cookie, "origin": base, "x-requested-with": "XMLHttpRequest"}
        ops = {}
        for slug, sent, tag in [("e2e-opa", SENT_A, "A"), ("e2e-opb", SENT_B, "B")]:
            st, _, _, _ = req(base, "PUT", f"/api/drafts/{slug}",
                              {"title": f"隔离{tag}", "date": "2026-10-25", "tags": [],
                               "body": draft_body(sent, tag), "rev": 0}, csrf)
            assert st == 200, f"存草稿 {slug} {st}"
            st, body, _, _ = req(base, "POST", "/api/preview", {"slug": slug}, csrf)
            assert st == 200, f"触发预览 {slug}: {st} {body[:200]}"
            j = json.loads(body)
            ops[tag] = j["opId"]
            ops["url" + tag] = j["url"]
        check("A0 触发链:两篇真实构建+注册", bool(ops.get("A") and ops.get("B")),
              f"opA={ops['A'][:12]}… opB={ops['B'][:12]}…")
        OP_A, OP_B, URL_A, URL_B = ops["A"], ops["B"], ops["urlA"], ops["urlB"]

        # ── R1 未登录 ──
        st, _, _, _ = req(base, "GET", URL_A)
        check("R1 未登录 HTML 401", st == 401, str(st))

        with sync_playwright() as pw:
            cand = Path.home() / "AppData/Local/ms-playwright"
            exe = {}
            if cand.is_dir():
                hits = [p for p in cand.glob("chromium-*/chrome-win64/chrome.exe")]
                if hits:
                    exe = {"executable_path": str(max(hits))}
            b = pw.chromium.launch(**exe)
            ctx = b.new_context(viewport={"width": 1280, "height": 900})
            pg = ctx.new_page()

            pg.goto(base + "/login")
            pg.fill("input[type=password]", PW_TEXT)
            pg.click("button[type=submit]")
            pg.wait_for_url("**/", timeout=8000)

            # ── R2 登录预览 ──
            pg.goto(base + URL_A)
            pg.wait_for_timeout(2500)
            body_text = pg.inner_text("body")
            check("R2 哨兵可见", SENT_A in body_text)
            check("R2 横幅", "草稿预览" in body_text)
            check("R2 对方哨兵不串入", SENT_B not in body_text)
            resp = ctx.request.get(base + URL_A)
            html_a = resp.text()
            check("R2 CSP=sandbox+noindex",
                  resp.headers.get("content-security-policy") == "sandbox"
                  and resp.headers.get("x-robots-tag") == "noindex")
            m_css = re.search(rf"/preview/{OP_A}/fonts/fonts\.css\?t=([A-Za-z0-9_-]+)", html_a)
            st, css_body, h_css, _ = req(base, "GET", f"/preview/{OP_A}/fonts/fonts.css?t={m_css.group(1)}")
            m_w = re.search(r"shards/([A-Za-z0-9._-]+\.woff2)\?t=([A-Za-z0-9_-]+)",
                            css_body.decode("utf-8"))
            st_w, _, h_w, _ = req(base, "GET",
                                  f"/preview/{OP_A}/fonts/shards/{m_w.group(1)}?t={m_w.group(2)}")
            check("R2 fonts.css 200", st == 200 and "text/css" in h_css.get("content-type", ""), str(st))
            check("R2 woff2 分片 200+ACAO:*",
                  st_w == 200 and h_w.get("access-control-allow-origin") == "*",
                  f"{st_w} acao={h_w.get('access-control-allow-origin')}")

            # ── R3 活动内容零执行(服务端请求记录) ──
            time.sleep(1.0)
            srv_log = log.read_text(encoding="utf-8", errors="replace")
            check("R3 脚本零执行(/api/pwn* 零到达)", "/api/pwn" not in srv_log)

            # ── R4 实际点击 ──
            url0 = pg.url
            log_len0 = len(log.read_text(encoding="utf-8", errors="replace"))
            for sel in ("a[data-wb-target='/posts/other/']",
                        "a[data-wb-target='https://example.com/x']"):
                assert pg.locator(sel).count() >= 1, f"反例断言失效:正文缺改写链接 {sel}"
                pg.click(sel, timeout=3000)
                pg.wait_for_timeout(600)
            time.sleep(0.5)
            new_log = log.read_text(encoding="utf-8", errors="replace")[log_len0:]
            new_prev = new_log.count("/preview/")
            check("R4 点击站内/外部:url 不变+零新 /preview 请求",
                  pg.url == url0 and new_prev == 0,
                  f"url_stable={pg.url == url0} new_prev={new_prev}")

            # ── R4b 页内锚点(正文 #bottom 链接必须存在并同文档滚动) ──
            assert pg.locator("a[href='#bottom']").count() >= 1, "正文锚点链接缺失"
            pg.locator("a[href='#bottom']").first.click(timeout=5000)
            pg.wait_for_timeout(400)
            scrolled = pg.evaluate("() => window.scrollY > 50")
            check("R4b 页内锚点滚动", scrolled is True)

            # ── R5 双预览 ──
            pg.goto(base + URL_B)
            pg.wait_for_timeout(1500)
            tb = pg.inner_text("body")
            check("R5 B 哨兵可见且不串 A", SENT_B in tb and SENT_A not in tb)

            # ── R6 登出连带失效 ──
            resp_html = ctx.request.get(base + URL_B)
            m = re.search(r"fonts\.css\?t=([A-Za-z0-9_-]+)", resp_html.text())
            tok = m.group(1)
            st_css, _, _, _ = req(base, "GET", f"/preview/{OP_B}/fonts/fonts.css?t={tok}")
            check("R6 前置:登出前 token 可用", st_css == 200, str(st_css))
            ctx.request.post(f"{base}/api/logout", headers={
                "origin": base, "x-requested-with": "XMLHttpRequest"})
            st2, _, _, _ = req(base, "GET", f"/preview/{OP_B}/fonts/fonts.css?t={tok}")
            st3, _, _, _ = req(base, "GET", URL_B)
            check("R6 登出:旧 token 401+HTML 401", st2 == 401 and st3 == 401,
                  f"css={st2} html={st3}")

            # ── R7 未注册/已删 410 ──
            st4, _, _, _ = req(base, "GET", "/preview/opGONE/")
            check("R7 不存在/已删预览 410", st4 == 410, str(st4))

            # ── BLOCK:阻断 fonts.css → 字体判据必须 FAIL ──
            blocked = previews_dir / OP_B / "fonts" / "fonts.css"
            if blocked.exists():
                blocked.rename(tmp / "fonts.css.blocked")
            st_b = req(base, "GET", f"/preview/{OP_B}/fonts/fonts.css")[0]
            check("BLOCK 阻断 fonts.css → 判据 FAIL(非 200)", st_b != 200, str(st_b))
            b.close()

        srv.terminate()
        srv.wait(timeout=5)
        failed = [n for n, ok, _ in ok_all if not ok]
        print(f"\n== e2e 预览隔离: {len(ok_all) - len(failed)}/{len(ok_all)} ==")
        sys.exit(1 if failed else 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
