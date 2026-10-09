# -*- coding: utf-8 -*-
"""site 浏览器验收(批次 1+,Playwright/Chromium;入库可复跑)。

前置:npm run build(验收 dist/);本机 playwright + chromium。
覆盖:页面矩阵(昼/夜 × 全站真实页)、手机 390、无 JS、键盘、reduced-
motion、直接访问与返回路径、文章页挂名、脚本入口数(应恰为 2:site.js
+ 首帧内联)、字体分片实际命中。只断言浏览器实测状态。
用法:python -I site/scripts/verify_browser.py [--port 8935]
"""
import http.server
import socketserver
import sys
import threading

from playwright.sync_api import sync_playwright

PORT = 8935
CHROME = (r"C:\Users\nanmu\AppData\Local\ms-playwright\chromium-1248"
          r"\chrome-win64\chrome.exe")

RESULTS = []


def check(label, ok, detail=""):
    RESULTS.append((label, ok))
    print("[%s] %s => %s" % (label, detail, "PASS" if ok else "FAIL"))


def serve(root):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


# (路径, 键, 导航 aria-current 期望)
PAGES = [
    ("/", "index", "/"),
    ("/posts/", "posts", "/posts/"),
    ("/posts/hello-nanmu-blog/", "post", "/posts/"),
    ("/digest/", "digest", "/digest/"),
    ("/about/", "about", "/about/"),
    ("/404.html", "404", None),
]


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    httpd = serve("dist")
    base = "http://127.0.0.1:%d" % PORT
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=CHROME)

            # ── A. 矩阵:昼(跟随系统浅色)/ 夜(localStorage dark) ──
            for theme in ("light", "dark"):
                ctx = b.new_context(viewport={"width": 1440, "height": 900})
                if theme == "dark":
                    ctx.add_init_script(
                        "try{localStorage.setItem('nm-theme','dark')}catch(e){}")
                errs = []
                for path, key, cur in PAGES:
                    pg = ctx.new_page()
                    pg.on("pageerror", lambda e: errs.append("%s:%s" % (key, e)))
                    font_urls = []
                    pg.on("response",
                          lambda r: font_urls.append(r.url)
                          if r.url.endswith(".woff2") else None)
                    pg.goto(base + path, wait_until="domcontentloaded")
                    pg.wait_for_timeout(300)
                    st = pg.evaluate("""(cur) => ({
                      top: !!document.querySelector('header.top'),
                      navLinks: document.querySelectorAll('nav.main a').length,
                      themeBtn: !!document.querySelector('#theme-btn'),
                      scripts: document.querySelectorAll('script').length,
                      cur: cur ? (document.querySelector(
                            'nav.main a[aria-current="page"]') || {href: null}).href
                            : 'n/a',
                      ox: document.documentElement.scrollWidth
                           - document.documentElement.clientWidth,
                      bg: getComputedStyle(document.body).backgroundColor,
                      dt: document.documentElement.dataset.theme || '',
                      title: document.title})""", cur)
                    ok = (st["top"] and st["navLinks"] >= 4 and st["themeBtn"]
                          and st["scripts"] == 2 and st["ox"] <= 0
                          and (cur is None or (st["cur"] or "").endswith(cur))
                          and st["title"] != "")
                    if theme == "dark":
                        ok = ok and st["dt"] == "dark" \
                            and st["bg"] != "rgb(240, 237, 229)"
                    if key == "post":
                        ok = ok and len(font_urls) >= 5  # 分片实际命中
                    check("matrix/%s/%s" % (key, theme), ok,
                          "nav=%d script=%d ox=%d fonts=%d cur=%s" %
                          (st["navLinks"], st["scripts"], st["ox"],
                           len(font_urls), st["cur"]))
                    pg.close()
                check("matrix/console/%s" % theme, not errs, str(errs[:3]))
                ctx.close()

            # ── B. 页面内容要点(昼) ──
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            pg.goto(base + "/posts/", wait_until="domcontentloaded")
            n = pg.evaluate("document.querySelectorAll('.row-item').length")
            h3 = pg.evaluate("(document.querySelector('.row-item h3')||{textContent:''}).textContent")
            check("posts/rows", n >= 1 and "你好" in h3, "rows=%d h3=%s" % (n, h3))
            sub = pg.evaluate("(document.querySelector('.subscribe')||{textContent:''}).textContent")
            check("posts/subscribe", "rss.xml" in sub, sub[:40])
            pg.goto(base + "/posts/hello-nanmu-blog/", wait_until="domcontentloaded")
            st = pg.evaluate("""() => {
              const ph = document.querySelector('.paper-head');
              return {
              head: !!ph,
              vt: ph ? getComputedStyle(ph).viewTransitionName : '(missing)',
              paras: document.querySelectorAll('.prose p').length,
              fin: !!document.querySelector('.colophon .fin'),
              none: document.querySelectorAll('.prev-next .none').length,
              bar: !!document.querySelector('.progress-bar')};}""")
            check("post/content", st["head"] and st["vt"] == "latest-cover"
                  and st["paras"] >= 3 and st["fin"] and st["none"] == 2
                  and st["bar"], str(st))
            pg.goto(base + "/digest/", wait_until="domcontentloaded")
            st = pg.evaluate("""() => ({
              blank: !!document.querySelector('.blank-sheet .bs-state'),
              state: (document.querySelector('.blank-sheet .bs-state')
                      || {textContent:''}).textContent,
              sub: (document.querySelector('.subscribe')||{textContent:''}).textContent})""")
            check("digest/blank", st["blank"] and "暂无" in st["state"]
                  and "digest.xml" in st["sub"],
                  "state=%s" % st["state"])
            pg.goto(base + "/about/", wait_until="domcontentloaded")
            st = pg.evaluate("""() => ({
              grid: !!document.querySelector('.about-grid'),
              todo: document.querySelectorAll('.todo-slot').length,
              svg: !!document.querySelector('.vignette svg'),
              facts: document.querySelectorAll('.fact-row').length})""")
            check("about/content", st["grid"] and st["todo"] >= 1 and st["svg"]
                  and st["facts"] >= 3, str(st))
            pg.goto(base + "/404.html", wait_until="domcontentloaded")
            st = pg.evaluate("""() => ({
              h1: (document.querySelector('.gate-wrap h1')||{textContent:''}).textContent,
              links: document.querySelectorAll('.gate-links a').length})""")
            check("404/gate", "没有" in st["h1"] or "不存在" in st["h1"]
                  or st["h1"] != "", st["h1"] + " links=%d" % st["links"])
            pg.close()
            ctx.close()

            # ── C. 手机 390:布局 + 菜单按钮接管 ──
            ctx = b.new_context(viewport={"width": 390, "height": 844})
            for path, key, _ in PAGES[:5]:
                pg = ctx.new_page()
                pg.goto(base + path, wait_until="domcontentloaded")
                pg.wait_for_timeout(200)
                st = pg.evaluate("""() => {
                  const mt = document.querySelector('.menu-toggle');
                  return {
                  ox: document.documentElement.scrollWidth
                    - document.documentElement.clientWidth,
                  toggle: mt ? getComputedStyle(mt).display : 'missing'};}""")
                check("mobile/%s" % key,
                      st["ox"] <= 0 and st["toggle"] not in ("none", "missing"),
                      "ox=%d toggle=%s" % (st["ox"], st["toggle"]))
                pg.close()
            ctx.close()

            # ── D. 无 JS:内容与导航完整 ──
            ctx = b.new_context(java_script_enabled=False,
                                viewport={"width": 1440, "height": 900})
            for path, key, sel in (("posts/", "posts", ".row-item h3"),
                                   ("posts/hello-nanmu-blog/", "post", ".prose p"),
                                   ("digest/", "digest", ".blank-sheet .bs-state"),
                                   ("about/", "about", ".about-grid .prose p")):
                pg = ctx.new_page()
                pg.goto(base + "/" + path, wait_until="domcontentloaded")
                st = pg.evaluate("""(sel) => {
                  const nav = document.querySelector('nav.main');
                  return {
                  content: !!document.querySelector(sel),
                  nav: nav ? getComputedStyle(nav).display : 'missing',
                  js: document.documentElement.classList.contains('js')};}""", sel)
                check("nojs/%s" % key, st["content"] and st["nav"] != "none"
                      and not st["js"],
                      "content=%s nav=%s js=%s" %
                      (st["content"], st["nav"], st["js"]))
                pg.close()
            ctx.close()

            # ── E. reduced-motion:过渡归零、404 静止 ──
            ctx = b.new_context(reduced_motion="reduce",
                                viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            pg.goto(base + "/posts/", wait_until="domcontentloaded")
            st = pg.evaluate("""() => {
              const a = document.querySelector('nav.main a');
              return {
              sb: getComputedStyle(document.documentElement).scrollBehavior,
              td: a ? getComputedStyle(a).transitionDuration : 'missing'};}""")
            dur = 0.0
            if st["td"] != "missing":
                dur = sum(float(x.strip().rstrip("ms").rstrip("s")) /
                          (1000.0 if x.strip().endswith("ms") else 1.0)
                          for x in st["td"].split(",") if x.strip())
            check("reduced/posts", st["sb"] == "auto" and st["td"] != "missing"
                  and dur < 0.001,
                  "scroll=%s dur=%s" % (st["sb"], st["td"]))
            pg.goto(base + "/404.html", wait_until="domcontentloaded")
            anim = pg.evaluate("""() => {
              const lift = document.querySelector('.gate .lift');
              return lift ? getComputedStyle(lift).animationName
                          : 'missing';}""")
            check("reduced/404", anim == "none", "anim=%s" % anim)
            pg.close()
            ctx.close()

            # ── F. 主题三态循环 + 持久化 ──
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            pg.goto(base + "/", wait_until="domcontentloaded")
            if pg.query_selector("#theme-btn"):
                seq = []
                for _ in range(3):
                    pg.click("#theme-btn")
                    pg.wait_for_timeout(120)
                    seq.append(pg.evaluate(
                        "document.documentElement.dataset.theme || 'auto'"))
                stored = pg.evaluate(
                    "try{localStorage.getItem('nm-theme')}catch(e){null}")
                pg.reload(wait_until="domcontentloaded")
                after = pg.evaluate(
                    "document.documentElement.dataset.theme || 'auto'")
                check("theme/cycle", seq == ["light", "dark", "auto"]
                      and stored == "auto" and after == "auto",
                      "seq=%s stored=%s after=%s" % (seq, stored, after))
            else:
                check("theme/cycle", False, "no #theme-btn")
            pg.close()
            ctx.close()

            # ── G. 连续路径:首页→文章→点进文章→返回,栏目链 aria-current 跟随 ──
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/", wait_until="domcontentloaded")
            try:
                pg.click("nav.main >> text=文章", timeout=5000)
                pg.wait_for_url("**/posts/", timeout=8000)
                pg.wait_for_selector(".row-item", timeout=8000)
                pg.click(".row-item")          # 点进唯一真实文章
                pg.wait_for_url("**/posts/hello-nanmu-blog/", timeout=8000)
                pg.wait_for_selector(".prose p", timeout=8000)
                pg.evaluate("history.back()")  # 返回文章目录
                pg.wait_for_url("**/posts/", timeout=8000)
                ok = True
                chain = [("nav.main >> text=日报", "/digest/"),
                         ("nav.main >> text=关于", "/about/")]
                for sel, url in chain:
                    pg.click(sel, timeout=5000)
                    pg.wait_for_url("**" + url, timeout=8000)
                    pg.wait_for_timeout(250)
                    got = pg.evaluate(
                        "(document.querySelector('nav.main a[aria-current=\"page\"]')||{href:null}).href")
                    if not (got or "").endswith(url):
                        ok = False
                check("path/chain", ok and not errs, "errs=%s" % errs[:2])
            except Exception as exc:  # noqa: BLE001 验收脚本:缺失即 FAIL
                check("path/chain", False, str(exc)[:80])
            pg.close()
            ctx.close()

            # ── H. 键盘:Tab 可达导航 ──
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            pg.goto(base + "/", wait_until="domcontentloaded")
            focused = []
            for _ in range(5):
                pg.keyboard.press("Tab")
                focused.append(pg.evaluate(
                    "(document.activeElement.className || document.activeElement.tagName)"))
            ok = any("brand" in c for c in focused) and any(
                "main" in c or c.lower() == "a" for c in focused)
            check("keyboard/tab", ok, str(focused))
            pg.close()
            ctx.close()
            b.close()
    finally:
        httpd.shutdown()

    fails = [l for l, ok in RESULTS if not ok]
    print("\n== %d/%d PASS ==" % (len(RESULTS) - len(fails), len(RESULTS)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
