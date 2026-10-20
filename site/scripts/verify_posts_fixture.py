# -*- coding: utf-8 -*-
"""非空文章夹具验收(批次 C 证据轮,入库可复跑)。

背景:批次 C 真撤稿后公开文章为零,verify_browser 的首页断言全部
固化为零文章空态——但「有文章时」的验收能力不能因此消失(用户
裁决:撤稿不等于永久删除非空验收)。本脚本以临时文章夹具(长标题
折行 + 长摘要 + 正常阅读入口)经真实 astro 构建,验证:

  1. 四方同源:data-article.url == 封面卡 href == 页签「读全文」href,
     封面卡标题 == 文章标题,文章页 200 且 h1 正确;
  2. hero 几何不变式(与 verify_browser T 段同款)在长标题下成立:
     矮窗不折超、竖排文字不压目录块;
  3. posts 列表 1 行、RSS items=1。

夹具只写入临时构建副本,绝不进入 site/src/content 正式内容源;
不重新公开被撤文章(夹具为独立虚构样文,标题/正文与任何真实文章
无关)。

用法(在 site/ 下,前置:现场 node_modules 可用):
python -I scripts/verify_posts_fixture.py
"""
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_browser import find_chrome  # noqa: E402 同目录脚本(-I 不自动加)

SITE = Path(__file__).resolve().parents[1]          # site/
PORT = 8975
RESULTS = []

SLUG = "fixture-post"
TITLE = "长标题夹具文章——验证非空状态下的首页布局与阅读入口"
BODY = ("这是一篇用于验收的临时夹具文章,不属于站点真实内容。它带着一个"
        "刻意拉长的标题与这段刻意拉长的摘要,用来确认非空状态下首页封面卡、"
        "页签面板、列表与文章详情仍然四方一致,长标题在矮视口折行时也不与"
        "目录块重叠。构建发生在临时副本,正式内容源零改动。")
FIXTURE_MD = (
    "---\ntitle: %s\npubDate: 2026-10-19\ntags: [随想, 验收]\ndraft: false\n---\n\n%s\n"
    % (TITLE, BODY))


def check(label, ok, detail=""):
    RESULTS.append((label, ok))
    print("[%s] %s => %s" % (label, detail, "PASS" if ok else "FAIL"))


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


def remove_junction(link):
    if not link.exists():
        return True
    try:
        os.rmdir(link)          # Windows junction:只删链接本身
    except OSError:
        try:
            link.unlink()
        except OSError:
            return False
    return not link.exists()


def clear_persistent_store():
    """同 verify_digest_states:防夹具条目残留污染真实构建。"""
    target = SITE / "node_modules" / ".astro"
    if not target.exists():
        return True
    real = os.path.realpath(str(target))
    site_real = os.path.realpath(str(SITE))
    if real == site_real or not real.startswith(site_real + os.sep):
        print("[posts-fx] data-store 解析后不在本 site 内,拒绝删除:%s" % real)
        return False
    shutil.rmtree(real, ignore_errors=True)
    return not target.exists()


def build_with_fixture_post(tmp):
    if tmp.exists():
        if not remove_junction(tmp / "node_modules"):
            raise RuntimeError("旧 junction 无法摘除,拒绝继续")
        shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(SITE, tmp, ignore=shutil.ignore_patterns(
        "node_modules", "dist", ".astro"))
    link = tmp / "node_modules"
    try:
        import _winapi
        _winapi.CreateJunction(str(SITE / "node_modules"), str(link))
    except (ImportError, OSError):
        os.symlink(str(SITE / "node_modules"), str(link))
    posts = tmp / "src" / "content" / "posts"
    posts.mkdir(parents=True, exist_ok=True)
    (posts / ("%s.md" % SLUG)).write_text(FIXTURE_MD, encoding="utf-8")
    try:
        r = subprocess.run(
            ["node", "node_modules/astro/astro.js", "build"],
            cwd=str(tmp), capture_output=True, encoding="utf-8",
            errors="replace", shell=False)
    finally:
        clear_persistent_store()
    if r.returncode != 0:
        print(r.stdout[-800:], r.stderr[-800:])
        return False
    return True


# 与 verify_browser T 段同款几何测量(副本,断言不依赖主脚本内部结构)
HERO_JS = """(() => {
  const r = (el) => { if (!el) return null;
    const b = el.getBoundingClientRect();
    return {x: b.x, y: b.y, right: b.right, bottom: b.bottom}; };
  const g = (s) => document.querySelector(s);
  const vt = g('.v-title');
  const fs = vt ? parseFloat(getComputedStyle(vt).fontSize) : 0;
  const clear = (a, c) => !a || !c ? null
    : !(a.right > c.x + 0.5 && a.bottom > c.y + 0.5
       && c.right > a.x + 0.5 && c.bottom > a.y + 0.5);
  const toc = r(g('.toc-block')), tabs = r(g('.page-tabs'));
  const vtR = r(vt), subR = r(g('.v-sub'));
  return {
    cols: (vt && fs) ? vt.getBoundingClientRect().width / (fs * 1.16) : null,
    kickClear: clear(r(g('.v-kicker')), toc),
    titleClear: clear(vtR, toc),
    subClear: clear(subR, toc),
    gap: (vtR && tabs) ? tabs.y - vtR.bottom : null,
    subGap: (subR && tabs) ? tabs.y - subR.bottom : null,
  };
})()"""


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="nanmu-postsfx-"))
    httpd = None
    try:
        if not build_with_fixture_post(tmp):
            check("posts-fx/build", False, "夹具构建失败")
            return 1
        check("posts-fx/build", True, "临时副本构建完成(正式源零改动)")
        httpd = serve(tmp / "dist", PORT)
        base = "http://127.0.0.1:%d" % PORT
        with sync_playwright() as p:
            launch = ({"executable_path": find_chrome()}
                      if find_chrome() else {})
            b = p.chromium.launch(**launch)

            # 1. 四方同源 + 阅读入口(长标题态)
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            pg.goto(base + "/", wait_until="domcontentloaded")
            pg.wait_for_function("document.fonts.status === 'loaded'",
                                 timeout=15000)
            pg.wait_for_timeout(900)
            st = pg.evaluate("""() => {
              const host = document.querySelector('#scene3d');
              const art = host && host.dataset.article
                ? JSON.parse(host.dataset.article) : null;
              const cover = document.querySelector('.cover-card');
              const read = document.querySelector('#panel-posts a.btn');
              return {
                art: art,
                coverHref: cover ? cover.getAttribute('href') : null,
                readHref: read ? read.getAttribute('href') : null,
                cbTitle: (document.querySelector('.cb-title')
                          || {textContent: ''}).textContent,
                fLabel: (document.querySelector('.f-label')
                         || {textContent: ''}).textContent};}""")
            art = st["art"] or {}
            check("posts-fx/source-4way",
                  art.get("url") == "/posts/%s/" % SLUG
                  and art["url"] == st["coverHref"] == st["readHref"]
                  and art.get("title") == TITLE
                  and art["title"] in st["cbTitle"],
                  "url=%s cover=%s read=%s title=%s"
                  % (art.get("url"), st["coverHref"], st["readHref"],
                     (art.get("title") or "")[:12]))

            # 2. hero 几何:长标题在矮窗/常规窗不压目录(T 段同款不变式)
            for vw, vh, tag, max_cols in ((1280, 600, "low600", 2),
                                          (1366, 768, "nb768", 1)):
                pg.set_viewport_size({"width": vw, "height": vh})
                pg.wait_for_timeout(500)
                g = pg.evaluate(HERO_JS)
                check("posts-fx/hero-%s" % tag,
                      g["cols"] is not None and g["cols"] <= max_cols + 0.3
                      and g["kickClear"] and g["titleClear"]
                      and g["subClear"] and g["gap"] >= -0.5
                      and g["subGap"] >= -0.5,
                      "cols=%.2f(max %d) gap=%s subGap=%s"
                      % (g["cols"] or -1, max_cols, g["gap"], g["subGap"]))
            pg.close()
            ctx.close()

            # 3. 列表 1 行;4. 文章页 200 + h1;5. RSS items=1
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            pg.goto(base + "/posts/", wait_until="domcontentloaded")
            rows = pg.evaluate("""() => [...document.querySelectorAll(
              '.row-item')].map(a => a.textContent.trim().slice(0, 14))""")
            check("posts-fx/list", len(rows) == 1 and TITLE[:8] in rows[0],
                  "rows=%s" % rows)
            resp = pg.goto(base + "/posts/%s/" % SLUG,
                           wait_until="domcontentloaded")
            h1 = pg.evaluate("(document.querySelector('.post h1')"
                             " || document.querySelector('h1')"
                             " || {textContent: ''}).textContent.trim()")
            check("posts-fx/post-page",
                  resp.status == 200 and TITLE in h1,
                  "status=%s h1=%s" % (resp.status, h1[:14]))
            rss = (tmp / "dist" / "rss.xml").read_text(encoding="utf-8")
            check("posts-fx/rss", rss.count("<item>") == 1
                  and TITLE in rss, "items=%d" % rss.count("<item>"))
            pg.close()
            ctx.close()
            b.close()
    finally:
        if httpd:
            httpd.shutdown()
        remove_junction(tmp / "node_modules")
        shutil.rmtree(tmp, ignore_errors=True)
        clear_persistent_store()

    fails = [l for l, ok in RESULTS if not ok]
    print("\n== %d/%d PASS ==" % (len(RESULTS) - len(fails), len(RESULTS)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
