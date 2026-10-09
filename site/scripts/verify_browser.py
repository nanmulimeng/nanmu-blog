# -*- coding: utf-8 -*-
"""site 浏览器验收(批次 2+,Playwright/Chromium;入库可复跑)。

前置:npm run build(验收 dist/);本机 playwright + chromium。
覆盖:页面矩阵(昼/夜 × 全站真实页)、手机 360/390/430、无 JS、键盘、
reduced-motion、直接访问与返回路径、文章页挂名、脚本入口数(内页 2:
site.js+首帧内联;首页 4:另加 home.js 与 boot6 模块)、字体分片实际命中
(仅 2xx + 中文样本逐字重 fonts.check 实测装载,含改名 NM Plex Mono)。
批次 2 增:首页静态结构/内容同源(#scene3d data-* JSON 与封面卡/
页签面板同源)、W5-W8 行为、3D 场景(__bookscene/select 双向/快速连选/
暂停组合)、WebGL 不可用零 3D 请求、模块失败终态、字体挂起超时接替、
封面挂名回程不残留。只断言浏览器实测状态。
浏览器:环境变量 NM_VERIFY_CHROME 指定 chrome 可执行文件;未设时扫描
ms-playwright 已装版本(取最大 build 号),再退 Playwright 默认解析——
不绑定固定用户名或 build 号。
用法:python -I site/scripts/verify_browser.py [--port 8935]
"""
import http.server
import os
import socketserver
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = 8935
SITE = Path(__file__).resolve().parents[1]  # site/


def find_chrome():
    """chrome 可执行:NM_VERIFY_CHROME 显式优先;退 ms-playwright 已装
    版本扫描(取最大 build 号);都没有则返回 None 交 Playwright 默认解析
    (其报错信息自带安装指引)。不绑定固定用户名或 build 号。"""
    explicit = os.environ.get("NM_VERIFY_CHROME")
    if explicit:
        return explicit
    home = Path.home()
    for base in (home / "AppData/Local/ms-playwright",
                 home / ".cache/ms-playwright"):
        if not base.is_dir():
            continue
        exes = []
        for d in base.glob("chromium-*"):
            for rel in (("chrome-win64", "chrome.exe"),
                        ("chrome-win", "chrome.exe"),
                        ("chrome-linux", "chrome"),
                        ("chrome-mac", "Chromium.app/Contents/MacOS/Chromium")):
                f = d.joinpath(*rel)
                if f.exists():
                    exes.append(f)
        if exes:
            def vkey(f):
                try:
                    return int(f.parent.parent.name.split("-")[-1])
                except ValueError:
                    return 0
            return str(max(exes, key=vkey))
    return None


CHROME = find_chrome()

RESULTS = []


def check(label, ok, detail=""):
    RESULTS.append((label, ok))
    print("[%s] %s => %s" % (label, detail, "PASS" if ok else "FAIL"))


def poll_js(pg, expr, timeout_ms, interval=250):
    """轮询求值 expr 直到真值或超时;返回最后一次取值。"""
    deadline = time.time() + timeout_ms / 1000.0
    val = None
    while time.time() < deadline:
        val = pg.evaluate(expr)
        if val:
            return val
        pg.wait_for_timeout(interval)
    return val


def serve(root, port=PORT, fonts_delay=0, hang_first_fonts=0):
    """fonts_delay>0:全部 /fonts/ 请求 sleep(模拟全站字体慢)。
    hang_first_fonts>0:前 N 个 .woff2 分片各 sleep 9s(N 段用——挂起
    少量分片触发 texReady 3.5s 超时接替,同时不占满 HTTP/1.1 的 6 连接
    池;全挂会把场景字节也饿到 40s+,测的是连接极限而非超时路径)。"""
    hang_n = [0]
    hang_lock = threading.Lock()

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def do_GET(self):
            if fonts_delay and "/fonts/" in self.path:
                time.sleep(fonts_delay)
            elif hang_first_fonts and self.path.endswith(".woff2"):
                with hang_lock:
                    i = hang_n[0]
                    hang_n[0] += 1
                if i < hang_first_fonts:
                    time.sleep(9)
            super().do_GET()

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, *a):
            pass
    class TS(socketserver.ThreadingTCPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            pass  # 本地验收:连接中断噪声不值得打印
    socketserver.TCPServer.allow_reuse_address = True
    httpd = TS(("127.0.0.1", port), H)
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
    httpd = serve(str(SITE / "dist"))
    base = "http://127.0.0.1:%d" % PORT
    try:
        with sync_playwright() as p:
            launch = ({"executable_path": CHROME} if CHROME else {})
            b = p.chromium.launch(**launch)

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
                    font_hits = []
                    pg.on("response",
                          lambda r: font_hits.append(r.ok)
                          if r.url.endswith(".woff2") else None)
                    pg.goto(base + path, wait_until="domcontentloaded")
                    pg.wait_for_timeout(300)
                    fontck = pg.evaluate("""async () => {
                      await document.fonts.ready;
                      const out = {};
                      const zh = '你好,世界——纸与印。';
                      for (const w of ['400', '600', '900']) {
                        try {
                          await document.fonts.load(`${w} 17px 'Noto Serif SC'`, zh);
                          out['w' + w] = document.fonts.check(`${w} 17px 'Noto Serif SC'`, zh);
                        } catch (e) { out['w' + w] = 'err'; }
                      }
                      try {
                        await document.fonts.load(`17px 'NM Plex Mono'`, 'nanmu 2026');
                        out.mono = document.fonts.check(`17px 'NM Plex Mono'`, 'nanmu 2026');
                      } catch (e) { out.mono = 'err'; }
                      return out;
                    }""") if key == "post" else None
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
                          and st["ox"] <= 0
                          and (cur is None or (st["cur"] or "").endswith(cur))
                          and st["title"] != "")
                    if theme == "dark":
                        ok = ok and st["dt"] == "dark" \
                            and st["bg"] != "rgb(240, 237, 229)"
                    if key == "post":
                        # 分片实际命中:≥5 个且全部 2xx;中文样本逐字重
                        # (400/600/900)与改名 mono 经 load+check 实测装载
                        ok = ok and sum(font_hits) >= 5 and all(font_hits) \
                            and fontck is not None and all(
                                v is True for v in fontck.values())
                    check("matrix/%s/%s" % (key, theme), ok,
                          "nav=%d script=%d ox=%d fonts=%d/%d fontck=%s cur=%s" %
                          (st["navLinks"], st["scripts"], st["ox"],
                           sum(font_hits), len(font_hits), fontck, st["cur"]))
                    # 脚本入口数单列(ADR-0010 白名单):内页恰 2(site.js
                    # +首帧内联);首页 4(+home.js 与 boot6 模块,批次 2)
                    exp_scripts = 4 if key == "index" else 2
                    check("matrix/%s/scripts/%s" % (key, theme),
                          st["scripts"] == exp_scripts,
                          "scripts=%d expect=%d" % (st["scripts"], exp_scripts))
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

            # ── C. 手机 360/390/430:布局 + 菜单按钮接管(首页含 hero)──
            for w in (360, 390, 430):
                ctx = b.new_context(viewport={"width": w, "height": 844})
                for path, key, _ in PAGES[:5]:
                    pg = ctx.new_page()
                    pg.goto(base + path, wait_until="domcontentloaded")
                    pg.wait_for_timeout(200)
                    st = pg.evaluate("""() => {
                      const mt = document.querySelector('.menu-toggle');
                      return {
                      ox: document.documentElement.scrollWidth
                        - document.documentElement.clientWidth,
                      toggle: mt ? getComputedStyle(mt).display : 'missing',
                      hero: !!document.querySelector('#scene3d')};}""")
                    check("mobile%s/%s" % (w, key),
                          st["ox"] <= 0
                          and st["toggle"] not in ("none", "missing")
                          and (key != "index" or st["hero"]),
                          "ox=%d toggle=%s hero=%s" %
                          (st["ox"], st["toggle"], st["hero"]))
                    pg.close()
                ctx.close()

            # ── D. 无 JS:内容与导航完整(首页:hero/文章面板/三层全开) ──
            ctx = b.new_context(java_script_enabled=False,
                                viewport={"width": 1440, "height": 900})
            for path, key, sel in (("", "index", None),
                                   ("posts/", "posts", ".row-item h3"),
                                   ("posts/hello-nanmu-blog/", "post", ".prose p"),
                                   ("digest/", "digest", ".blank-sheet .bs-state"),
                                   ("about/", "about", ".about-grid .prose p")):
                pg = ctx.new_page()
                pg.goto(base + "/" + path, wait_until="domcontentloaded")
                if key == "index":
                    st = pg.evaluate("""() => ({
                      hero: !!document.querySelector('#scene3d'),
                      posters: document.querySelectorAll('#scene3d img.poster').length,
                      panelPosts: !(document.getElementById('panel-posts')
                          || {hasAttribute: () => true}).hasAttribute('hidden'),
                      readBtn: !!document.querySelector('#panel-posts a.btn'),
                      bodies: Array.from(document.querySelectorAll('.li-body'))
                          .filter(b => !b.hasAttribute('hidden')).length,
                      cover: !!document.querySelector('.cover-card'),
                      js: document.documentElement.classList.contains('js')})""")
                    check("nojs/index",
                          st["hero"] and st["posters"] == 2
                          and st["panelPosts"] and st["readBtn"]
                          and st["bodies"] == 3 and st["cover"] and not st["js"],
                          "hero=%s posters=%d panel=%s read=%s bodies=%d js=%s"
                          % (st["hero"], st["posters"], st["panelPosts"],
                             st["readBtn"], st["bodies"], st["js"]))
                    pg.close()
                    continue
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

            # ── I. 首页静态结构 + 内容同源(昼,桌面)──
            # 内容同源契约:#scene3d 的 data-article JSON 与封面卡 href、
            # 页签面板「读全文」href、featured 标题四方一致;poster 为
            # 装饰性主视觉(alt 不提文章标题),先于任何 3D 字节请求。
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            pg.goto(base + "/", wait_until="domcontentloaded")
            st = pg.evaluate("""() => {
              const host = document.querySelector('#scene3d');
              const art = host && host.dataset.article
                ? JSON.parse(host.dataset.article) : null;
              const posters = Array.from(
                document.querySelectorAll('#scene3d img.poster'));
              const light = posters.find(p => p.classList.contains('poster-light'));
              const cover = document.querySelector('.cover-card');
              const read = document.querySelector('#panel-posts a.btn');
              return {
              hero: !!host, heroClass: host ? host.className : '',
              h1: (document.querySelector('.hero-title h1')
                   || {textContent: ''}).textContent.trim(),
              posters: posters.length,
              lightAlt: light ? light.alt : '(missing)',
              fp: light ? (light.getAttribute('fetchpriority') || '') : '',
              lazy: light ? (light.getAttribute('loading') || '') : '',
              darkLazy: (document.querySelector('img.poster-dark')
                  || {getAttribute: () => null})
                  .getAttribute('loading'),
              tabs: document.querySelectorAll('.ptab').length,
              panels: document.querySelectorAll('.tpanel').length,
              panelPostsOn: !(document.getElementById('panel-posts')
                  || {hasAttribute: () => true}).hasAttribute('hidden'),
              knots: Array.from(document.querySelectorAll('.thread .knot'))
                  .map(k => k.dataset.for),
              coverHref: cover ? cover.getAttribute('href') : null,
              coverVT: cover ? cover.style.viewTransitionName : '(missing)',
              cbTitle: (document.querySelector('.cb-title')
                   || {textContent: ''}).textContent,
              readHref: read ? read.getAttribute('href') : null,
              layers: document.querySelectorAll('.layer-item').length,
              copies: document.querySelectorAll('.subscribe-zone .copy-link').length,
              digestState: (document.querySelector('.digest-empty .bs-state')
                   || {textContent: ''}).textContent,
              article: art};}""")
            art = st["article"] or {}
            ok = (st["hero"] and "hero-full" in (st["heroClass"] or "")
                  and st["h1"] != "" and st["posters"] == 2
                  and st["lightAlt"] != "" and st["fp"] == "high"
                  and st["lazy"] == "" and st["darkLazy"] == "lazy"
                  and st["tabs"] == 3 and st["panels"] == 3
                  and st["panelPostsOn"]
                  and st["knots"] == ["#posts", "#digest", "#about", "#subscribe"]
                  and st["coverVT"] == "" and st["copies"] == 2
                  and "暂无" in st["digestState"])
            if art:
                # 四方同源 + 装饰性 alt(不含文章标题)
                ok = ok and art.get("url") and art["url"] == st["coverHref"] \
                    == st["readHref"] and st["cbTitle"].replace("\n", "") \
                    and art.get("title") in st["cbTitle"].replace("\n", "") \
                    and art.get("title", "X") not in st["lightAlt"]
            check("home/static", ok,
                  "hero=%s posters=%d fp=%s lazy=%s/%s tabs=%d/%d knots=%d"
                  " copies=%d art.url=%s cover=%s read=%s" %
                  (st["hero"], st["posters"], st["fp"], st["lazy"],
                   st["darkLazy"], st["tabs"],
                   st["panels"], len(st["knots"]), st["copies"],
                   (art or {}).get("url"), st["coverHref"], st["readHref"]))
            # 无静态/残留挂名:封面卡与页头之外的元素不挂 latest-cover
            extra_vt = pg.evaluate(
                "[...document.querySelectorAll('[style*=view-transition-name],"
                ".vt-named')].length")
            check("home/vt-clean", extra_vt == 0, "vt-named=%s" % extra_vt)
            pg.close()
            ctx.close()

            # ── J. W5-W8 页面侧行为(home.js;昼,桌面)──
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/", wait_until="domcontentloaded")
            pg.wait_for_timeout(300)
            present = pg.evaluate(
                "!!document.querySelector('#scene3d')"
                " && !!document.getElementById('panel-digest')")
            if not present:
                for lbl in ("home/tabs", "home/tabs-keyboard", "home/layers"):
                    check(lbl, False, "#scene3d/页签面板缺失")
                check("home/console", not errs, str(errs[:2]))
            else:
                st = pg.evaluate("""() => {
                  const t = document.querySelector('#tab-digest');
                  return {tab: t ? t.tabIndex : '(missing)',
                          sel: t ? t.getAttribute('aria-selected') : '',
                          hidden: document.getElementById('panel-digest')
                              .hasAttribute('hidden')};}""")
                pg.click("#tab-digest")
                pg.wait_for_timeout(150)
                st2 = pg.evaluate("""() => ({
                  sel: document.querySelector('#tab-digest')
                      .getAttribute('aria-selected'),
                  tab: document.querySelector('#tab-digest').tabIndex,
                  postsTab: document.querySelector('#tab-posts').tabIndex,
                  digestOn: !document.getElementById('panel-digest')
                      .hasAttribute('hidden'),
                  postsHidden: document.getElementById('panel-posts')
                      .hasAttribute('hidden')})""")
                check("home/tabs", st["tab"] == -1 and st["sel"] == "false"
                      and st["hidden"] and st2["sel"] == "true"
                      and st2["tab"] == 0 and st2["postsTab"] == -1
                      and st2["digestOn"] and st2["postsHidden"],
                      "before(tab=%s sel=%s) after(sel=%s tab=%s postsTab=%s "
                      "on=%s postsHidden=%s)" % (st["tab"], st["sel"],
                      st2["sel"], st2["tab"], st2["postsTab"],
                      st2["digestOn"], st2["postsHidden"]))
                # 键盘漫游:End 直达末页签
                pg.click("#tab-posts")
                pg.keyboard.press("End")
                pg.wait_for_timeout(120)
                kb = pg.evaluate("""() => ({
                  sel: (document.querySelector('#tab-about')
                      || {getAttribute: () => null})
                      .getAttribute('aria-selected'),
                  focus: document.activeElement.id})""")
                check("home/tabs-keyboard", kb["sel"] == "true"
                      and kb["focus"] == "tab-about", str(kb))
                # W8:三层手风琴(点层头)与分层图联动(点图卡)
                pg.click(".layer-item[data-layer=digest] .li-head")
                pg.wait_for_timeout(120)
                ly = pg.evaluate("""() => ({
                  dOn: (document.querySelector(
                      '.layer-item[data-layer=digest]')
                      || {classList: {contains: () => false}})
                      .classList.contains('on'),
                  pOff: !(document.querySelector(
                      '.layer-item[data-layer=posts]')
                      || {classList: {contains: () => true}})
                      .classList.contains('on'),
                  bodyOpen: !(document.querySelector(
                      '.layer-item[data-layer=digest] .li-body')
                      || {hasAttribute: () => true})
                      .hasAttribute('hidden')})""")
                pg.click(".layers-fig .ly-search")
                pg.wait_for_timeout(120)
                ly2 = pg.evaluate("""() => ({
                  sOn: (document.querySelector(
                      '.layer-item[data-layer=search]')
                      || {classList: {contains: () => false}})
                      .classList.contains('on'),
                  pressed: (document.querySelector('.ly-search')
                      || {getAttribute: () => null})
                      .getAttribute('aria-pressed')})""")
                check("home/layers", ly["dOn"] and ly["pOff"] and ly["bodyOpen"]
                      and ly2["sOn"] and ly2["pressed"] == "true",
                      "head=%s fig=%s" % (ly, ly2))
                check("home/console", not errs, str(errs[:2]))
            pg.close()
            ctx.close()

            # ── K. 3D 场景(批次 2 终态:boot→联动→连选→暂停组合)──
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/", wait_until="domcontentloaded")
            # boot 终态 = __bookscene 就绪且 poster 已退场(remove 有
            # 700ms 淡出定时器,合并进同一个 poll 等到终态)
            boot = poll_js(pg, "!!window.__bookscene"
                           " && document.querySelectorAll('#scene3d img.poster')"
                           ".length === 0", 15000)
            pg.wait_for_timeout(300)
            st = pg.evaluate("""(() => {
              const s = window.__bookscene;
              if (!s) return {boot: false};
              const pbb = s.projectBindingBottom();
              return {boot: true,
                      tris: s.stats().triangles,
                      posters: document.querySelectorAll('#scene3d img.poster').length,
                      hud: document.querySelectorAll('.scene-hud button').length,
                      pbb: pbb ? [pbb.x, pbb.y] : null};})()""")
            check("home3d/boot", bool(boot) and st.get("boot")
                  and st.get("tris", 0) > 0 and st.get("posters") == 0
                  and st.get("hud") == 2 and st.get("pbb"),
                  "book=%s tris=%s posters=%s hud=%s pbb=%s" %
                  (bool(boot), st.get("tris"), st.get("posters"),
                   st.get("hud"), st.get("pbb")))
            if not boot:
                for lbl in ("home3d/tab-to-scene", "home3d/scene-to-tab",
                            "home3d/fast-select", "home3d/reselect",
                            "home3d/pause-combo"):
                    check(lbl, False, "无 __bookscene(3D 未接入)")
            else:
                # 页签 → 3D(点击 tab 后场景 current 跟随)
                pg.click("#tab-digest")
                cur = poll_js(pg, "window.__bookscene"
                              " && window.__bookscene.current() === 'digest'",
                              4000)
                check("home3d/tab-to-scene", bool(cur), "current=%s"
                      % pg.evaluate("window.__bookscene.current()"))
                # 3D → 页签(select 后 tab aria-selected 同步)
                pg.evaluate("window.__bookscene.select('about')")
                tabok = poll_js(pg, "(document.querySelector('#tab-about')"
                               " || {getAttribute: () => null})"
                               ".getAttribute('aria-selected') === 'true'",
                               4000)
                check("home3d/scene-to-tab", bool(tabok), "about selected=%s"
                      % pg.evaluate("(document.querySelector('#tab-about')"
                                    " || {getAttribute: () => null})"
                                    ".getAttribute('aria-selected')"))
                # 快速连选:只保留最后一次
                pg.evaluate("window.__bookscene.select('posts');"
                            "window.__bookscene.select('digest');"
                            "window.__bookscene.select('about')")
                fast = poll_js(pg, "window.__bookscene.current() === 'about'"
                               " && (document.querySelector('#tab-about')"
                               " || {getAttribute: () => null})"
                               ".getAttribute('aria-selected') === 'true'",
                               4000)
                check("home3d/fast-select", bool(fast), "current=%s"
                      % pg.evaluate("window.__bookscene.current()"))
                # 选回正在进入前景的页(动画中重复同目标)
                pg.evaluate("window.__bookscene.select('posts')")
                pg.wait_for_timeout(200)
                pg.evaluate("window.__bookscene.select('posts')")
                reSel = poll_js(pg, "window.__bookscene.current() === 'posts'",
                                4000)
                check("home3d/reselect", bool(reSel), "current=%s"
                      % pg.evaluate("window.__bookscene.current()"))
                # 暂停→选择→拖拽→resize→复位→恢复(needsLoop 下即时重绘)。
                # select 在换页动画中只排队(pendingSelect),current() 要等
                # 排队链消化——用 poll 等到 current 终态,不赌立即生效
                st = pg.evaluate("""(() => {
                  const s = window.__bookscene;
                  s.setAmbient(false);
                  return {paused: s.isAmbientOn()};})()""")
                pg.evaluate("window.__bookscene.select('digest')")
                curOk = poll_js(pg, "window.__bookscene"
                                ".current() === 'digest'", 6000)
                st["cur"] = pg.evaluate("window.__bookscene.current()")
                cv = pg.query_selector("#scene3d canvas")
                if cv:
                    box = cv.bounding_box()
                    if box:
                        cx, cy = box["x"] + box["width"] / 2, box["y"] + 30
                        pg.mouse.move(cx, cy)
                        pg.mouse.down()
                        pg.mouse.move(cx + 60, cy + 20, steps=5)
                        pg.mouse.up()
                pg.set_viewport_size({"width": 1280, "height": 800})
                pg.wait_for_timeout(200)
                st2 = pg.evaluate("""(() => {
                  const s = window.__bookscene;
                  s.resetView();
                  s.setAmbient(true);
                  const pbb = s.projectBindingBottom();
                  return {amb: s.isAmbientOn(), cur: s.current(),
                          tris: s.stats().triangles,
                          pbb: pbb ? [pbb.x, pbb.y] : null};})()""")
                check("home3d/pause-combo", st["paused"] is False
                      and curOk and st["cur"] == "digest"
                      and st2["amb"] is True
                      and st2["cur"] == "digest" and st2["tris"] > 0
                      and st2["pbb"] and not errs,
                      "paused=%s cur=%s amb=%s cur2=%s tris=%s pbb=%s errs=%s"
                      % (st["paused"], st["cur"], st2["amb"], st2["cur"],
                         st2["tris"], st2["pbb"], errs[:2]))
            pg.close()
            ctx.close()

            # ── L. WebGL 不可用:零 3D 请求,poster 常显,页签仍切换 ──
            b2 = p.chromium.launch(
                **({"executable_path": CHROME} if CHROME else {}),
                args=["--disable-webgl", "--disable-webgl2"])
            try:
                ctx = b2.new_context(viewport={"width": 1440, "height": 900})
                pg = ctx.new_page()
                reqs = []
                pg.on("request", lambda r: reqs.append(r.url))
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(base + "/", wait_until="domcontentloaded")
                pg.wait_for_timeout(2500)
                st = pg.evaluate("""() => ({
                  noWebgl: (document.querySelector('#scene3d')
                      || {classList: {contains: () => false}})
                      .classList.contains('no-webgl'),
                  posters: document.querySelectorAll('#scene3d img.poster').length,
                  hud: !!document.querySelector('.scene-hud')})""")
                pg.click("#tab-digest", timeout=3000)
                pg.wait_for_timeout(150)
                tabok = pg.evaluate(
                    "!(document.getElementById('panel-digest')"
                    " || {hasAttribute: () => true}).hasAttribute('hidden')")
                # boot6 是探测入口(module 标签必然加载,gzip ~2.7KB),
                # 不属场景资源;断言语义=WebGL 不可用时零 three/scene 请求
                three = [u for u in reqs if "/3d/" in u
                         and "poster" not in u and "boot6" not in u]
                poster = [u for u in reqs if "poster" in u]
                check("home3d/no-webgl", st["noWebgl"] and st["posters"] >= 1
                      and not st["hud"] and tabok and not three and poster
                      and not errs,
                      "no-webgl=%s posters=%d hud=%s tab=%s 3d-reqs=%d "
                      "poster-reqs=%d errs=%s" %
                      (st["noWebgl"], st["posters"], st["hud"], tabok,
                       len(three), len(poster), errs[:2]))
                pg.close()
                ctx.close()
            except Exception as exc:  # noqa: BLE001 验收脚本:缺失即 FAIL
                check("home3d/no-webgl", False, str(exc)[:80])
            b2.close()

            # ── M. 模块失败(scene6 abort):.no-webgl 终态,poster 常显 ──
            try:
                ctx = b.new_context(viewport={"width": 1440, "height": 900})
                pg = ctx.new_page()
                pg.route("**/3d/scene6.js", lambda r: r.abort())
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(base + "/", wait_until="domcontentloaded")
                pg.wait_for_timeout(2500)
                st = pg.evaluate("""() => ({
                  noWebgl: (document.querySelector('#scene3d')
                      || {classList: {contains: () => false}})
                      .classList.contains('no-webgl'),
                  posters: document.querySelectorAll('#scene3d img.poster').length,
                  hud: !!document.querySelector('.scene-hud')})""")
                pg.click("#tab-about", timeout=3000)
                pg.wait_for_timeout(150)
                tabok = pg.evaluate(
                    "!(document.getElementById('panel-about')"
                    " || {hasAttribute: () => true}).hasAttribute('hidden')")
                check("home3d/module-fail", st["noWebgl"] and st["posters"] >= 1
                      and not st["hud"] and tabok and not errs,
                      "no-webgl=%s posters=%d hud=%s tab=%s errs=%s" %
                      (st["noWebgl"], st["posters"], st["hud"], tabok,
                       errs[:2]))
                pg.close()
                ctx.close()
            except Exception as exc:  # noqa: BLE001 验收脚本:缺失即 FAIL
                check("home3d/module-fail", False, str(exc)[:80])

            # ── N. 字体分片挂起:texReady 3.5s 超时后素纸场景接替 poster ──
            httpd_slow = serve(str(SITE / "dist"), PORT + 1, hang_first_fonts=2)
            slow_base = "http://127.0.0.1:%d" % (PORT + 1)
            try:
                ctx = b.new_context(viewport={"width": 1440, "height": 900})
                pg = ctx.new_page()
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(slow_base + "/", wait_until="domcontentloaded",
                        timeout=30000)
                # 窗口 20s:挂起分片让 rIC 与 race 顺延(DCL~1s + idle 至
                # 迟~10s + import + race 3.5s + poster 淡出 0.7s),终态不变。
                # 表达式必须纯布尔:poll_js 按真值返回,'pending' 之类的
                # 中间态字符串是真值,会第一次求值到就短路提前返回
                hung = poll_js(pg, "!!window.__bookscene"
                               " && document.querySelectorAll("
                               "'#scene3d img.poster').length === 0", 20000)
                after = pg.evaluate(
                    "({book: !!window.__bookscene, posters: "
                    "document.querySelectorAll('#scene3d img.poster').length})")
                check("home3d/font-hang", bool(hung) and not errs,
                      "book=%s posters=%s errs=%s"
                      % (after["book"], after["posters"], errs[:2]))
                pg.close()
                ctx.close()
            finally:
                httpd_slow.shutdown()

            # ── O. 封面挂名生命周期:两条去程回程后均不残留 ──
            try:
                ctx = b.new_context(viewport={"width": 1440, "height": 900})
                pg = ctx.new_page()
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                ok = True
                details = []
                for label, sel in (("cover", ".cover-card"),
                                   ("readbtn", ".featured .f-actions a.btn")):
                    pg.goto(base + "/", wait_until="domcontentloaded")
                    pg.wait_for_selector(sel, timeout=8000)
                    pg.click(sel)
                    # glob 的 * 不跨 "/",pathname 断言更直接
                    pg.wait_for_function(
                        "location.pathname.startsWith('/posts/')",
                        timeout=8000)
                    head = pg.evaluate(
                        "getComputedStyle(document.querySelector('.paper-head')"
                        " || document.body).viewTransitionName")
                    pg.evaluate("history.back()")
                    pg.wait_for_function("location.pathname === '/'",
                                         timeout=8000)
                    pg.wait_for_timeout(1200)  # VT finished 后摘除
                    vt = pg.evaluate(
                        "(document.querySelector('.cover-card')"
                        "||{style:{}}).style.viewTransitionName")
                    details.append("%s:head=%s back=%s" % (label, head, vt))
                    ok = ok and head == "latest-cover" and vt == ""
                check("home/cover-vt", ok and not errs, " ".join(details)
                      + " errs=%s" % errs[:2])
                pg.close()
                ctx.close()
            except Exception as exc:  # noqa: BLE001 验收脚本:缺失即 FAIL
                check("home/cover-vt", False, str(exc)[:80])
            b.close()
    finally:
        httpd.shutdown()

    fails = [l for l, ok in RESULTS if not ok]
    print("\n== %d/%d PASS ==" % (len(RESULTS) - len(fails), len(RESULTS)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
