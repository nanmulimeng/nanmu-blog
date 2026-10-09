# -*- coding: utf-8 -*-
"""site 资源预算测量(Playwright/Chromium;入库可复跑,只报实测数)。

口径(INTEGRATION-PLAN §5;2026-10-09 审计修正:三类证据分开,失败单列):
  A. 冷缓存分类体积——全新 context 首访内页,仅计 2xx 响应,按 html/css/
     js/woff2 分类合计(本地服务无压缩=原始字节);非 2xx 单列,不入分类;
  B. 跨页唯一资源增量——同 context 顺序访问其余三页,统计此前未出现的
     资源 URL 及字节。这是唯一 URL 去重口径:回答"该页引入了哪些新
     资源",不证明既有资源的缓存命中,不得据此宣称复用成立;
  C. 真实暖缓存传输——可缓存服务(Cache-Control: public, max-age=3600)
     下用 CDP Network 记录 fromDiskCache 与 encodedDataLength:冷访文章页
     装载字体后,重访同页与跨页的实际网络字节、磁盘缓存命中数;
  D. fonts.css 原始与 gzip 体积(gzip level 6、mtime=0,Python zlib——
     固定工具与等级,不同实现的数字不混比);
  E. 首页批次 2 预算——E1 请求时间线(CDP requestWillBeSent 发起序:
     poster <img> 必须先于任何 3D 资源请求,且仅当前主题单张 poster;
     INTEGRATION-PLAN §5 触发顺序断言,不靠 defer 语义自证);E2 资产
     分型(3D 四件 gzip-6 ≤220KB;poster 两张合计 ≤450KB)。
浏览器:环境变量 NM_VERIFY_CHROME 指定 chrome 可执行文件;未设时扫描
ms-playwright 已装版本(取最大 build 号),再退 Playwright 默认解析——
不绑定固定用户名或 build 号。
用法:python -I site/scripts/measure_budget.py [--port 8936]
"""
import argparse
import gzip
import http.server
import os
import socketserver
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

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


def serve(root, port, cache_control):
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=root, **k)

        def end_headers(self):
            self.send_header("Cache-Control", cache_control)
            super().end_headers()

        def log_message(self, *a):
            pass
    class TS(socketserver.ThreadingTCPServer):
        daemon_threads = True

        def handle_error(self, request, client_address):
            pass  # 本地测量:连接中断噪声不值得打印
    socketserver.TCPServer.allow_reuse_address = True
    httpd = TS(("127.0.0.1", port), H)
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


def fetch(page, url, seen):
    """访问 url,返回 (本页 2xx 分类字节, 新增唯一 URL 分型字节, 失败列表)。

    seen 跨调用共享:新增 = 本页出现且此前未见过的 URL(去重口径)。
    """
    page_bytes = {}
    new_urls = {}
    fails = []

    def on_resp(r):
        if r.request.resource_type != "document" and not r.url.endswith(
                (".css", ".js", ".woff2")):
            return
        if not r.ok:
            fails.append((classify(r.url), r.status, r.url))
            return
        kind = classify(r.url)
        n = size_of(r)
        page_bytes[kind] = page_bytes.get(kind, 0) + n
        if r.url not in seen:
            seen.add(r.url)
            new_urls[kind] = new_urls.get(kind, 0) + n

    page.on("response", on_resp)
    page.goto(url, wait_until="networkidle")
    page.remove_listener("response", on_resp)
    return page_bytes, new_urls, fails


def cdp_probe(ctx, page):
    """CDP Network 监听:按 requestId 关联 fromDiskCache 与实际传输字节。"""
    rec = {}
    cdp = ctx.new_cdp_session(page)

    def on_resp(e):
        r = e["response"]
        if r["url"].startswith("http"):
            rec[e["requestId"]] = {"url": r["url"], "status": r["status"],
                                   "disk": bool(r.get("fromDiskCache")),
                                   "mem": bool(r.get("fromMemoryCache")),
                                   "enc": 0}

    def on_fin(e):
        v = rec.get(e["requestId"])
        if v is not None:
            v["enc"] = e.get("encodedDataLength", 0)

    cdp.on("Network.responseReceived", on_resp)
    cdp.on("Network.loadingFinished", on_fin)
    cdp.send("Network.enable")
    return cdp, rec


def net_summary(rec):
    """(请求数, 零传输命中数, 实际网络字节, 失败列表)。

    实测(Chromium 1248):内存/磁盘命中的资源请求普遍不置
    fromDiskCache/fromMemoryCache,但 encodedDataLength=0 且 2xx——以
    「零传输且成功」为命中信号;fromDiskCache/fromMemoryCache 仍记录,
    仅作辅助。网络字节含响应头(encodedDataLength 口径)。
    """
    vals = list(rec.values())
    hits = sum(1 for v in vals if v["enc"] == 0 and v["status"] < 400)
    net = sum(v["enc"] for v in vals)
    fails = [(v["status"], v["url"]) for v in vals if v["status"] >= 400]
    return len(vals), hits, net, fails


def kib(n):
    return "%.1f KiB" % (n / 1024)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8936)
    args = ap.parse_args()

    fonts_css = SITE / "public/fonts/fonts.css"
    httpd = serve(str(SITE / "dist"), args.port, "no-store")
    httpd2 = serve(str(SITE / "dist"), args.port + 1, "public, max-age=3600")
    base = "http://127.0.0.1:%d" % args.port
    cache_base = "http://127.0.0.1:%d" % (args.port + 1)
    try:
        with sync_playwright() as p:
            launch = ({"executable_path": CHROME} if CHROME else {})
            b = p.chromium.launch(**launch)

            # ── A. 冷缓存分类体积 + B. 跨页唯一资源增量(no-store 服务)──
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            seen = set()
            cold, _, fails_a = fetch(pg, base + "/posts/hello-nanmu-blog/", seen)
            total = sum(cold.values())
            print("A 冷缓存 /posts/hello-nanmu-blog/(仅 2xx,原始字节):")
            for k in ("html", "css", "js", "woff2", "other"):
                if k in cold:
                    print("   %-6s %8d B" % (k, cold[k]))
            print("   合计   %8d B(%s)" % (total, kib(total)))
            print("   失败响应 %d 个%s" % (len(fails_a),
                  "" if not fails_a else " -> " + str(fails_a[:4])))
            print("A 口径注:HTML+CSS+JS(不含 woff2)= %d B(%s)"
                  % (total - cold.get("woff2", 0),
                     kib(total - cold.get("woff2", 0))))

            print("B 跨页唯一资源增量(同 context,唯一 URL 去重,非缓存证据):")
            for path in ("/posts/", "/digest/", "/about/"):
                _, new_u, fails_b = fetch(pg, base + path, seen)
                parts = " + ".join("%s %d B" % (k, v)
                                   for k, v in sorted(new_u.items())) or "无新增"
                print("   %-9s 新增:%s%s" % (
                    path, parts,
                    "" if not fails_b else " [失败 %d]" % len(fails_b)))
            pg.close()
            ctx.close()

            # ── C. 真实暖缓存传输(可缓存服务,CDP 实测)──
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            cdp, rec = cdp_probe(ctx, pg)
            seq = [("冷访", "/posts/hello-nanmu-blog/"),
                   ("重访", "/posts/hello-nanmu-blog/"),
                   ("暖访", "/posts/"), ("暖访", "/digest/"), ("暖访", "/about/")]
            print("C 真实暖缓存传输(Cache-Control: max-age=3600,CDP 实测,"
                  "网络字节含响应头):")
            for label, path in seq:
                rec.clear()
                pg.goto(cache_base + path, wait_until="networkidle")
                n, hits, net, fails_c = net_summary(rec)
                print("   %s %-28s 请求 %3d(零传输命中 %3d),"
                      "网络字节 %7d B(%s)%s"
                      % (label, path, n, hits, net, kib(net),
                         "" if not fails_c else
                         " [失败 %d: %s]" % (len(fails_c),
                                             fails_c[0][1].split("/")[-1])))
            pg.close()
            ctx.close()

            # ── E1. 首页请求时间线:poster 先于任何 3D 字节(发起序)──
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()
            cdp2 = ctx.new_cdp_session(pg)
            order = []

            def on_req(e):
                try:  # 部分 Network 事件无 params(如 V2 变体),跳过
                    order.append(e["params"]["request"]["url"])
                except (KeyError, TypeError):
                    pass
            cdp2.on("Network.requestWillBeSent", on_req)
            cdp2.send("Network.enable")
            pg.goto(base + "/", wait_until="domcontentloaded")
            deadline = time.time() + 20
            while time.time() < deadline:
                if pg.evaluate("!!window.__bookscene"):
                    break
                pg.wait_for_timeout(250)
            pg.wait_for_timeout(500)
            poster_reqs = [(i, u) for i, u in enumerate(order) if "poster" in u]
            three_reqs = [(i, u) for i, u in enumerate(order)
                          if "/3d/" in u and "poster" not in u]
            print("E1 首页请求时间线(CDP 发起序;昼上下文,期望仅 "
                  "poster-light 单张):")
            for i, u in poster_reqs:
                print("   poster  #%d %s" % (i, u.rsplit("/", 1)[-1]))
            for i, u in three_reqs:
                print("   3d      #%d %s" % (i, u.rsplit("/", 1)[-1]))
            ok_order = (len(poster_reqs) == 1
                        and "poster-light" in poster_reqs[0][1]
                        and len(three_reqs) >= 2
                        and poster_reqs[0][0] < min(i for i, _ in three_reqs))
            print("   poster 单张且先于 3D:%s%s"
                  % ("✓" if ok_order else "✗",
                     "" if three_reqs else "(无 3D 请求——场景未接入?)"))
            pg.close()
            ctx.close()
            b.close()
    finally:
        httpd.shutdown()
        httpd2.shutdown()

    # D. fonts.css 磁盘体积(固定 gzip level 6 / mtime=0,Python zlib)
    if fonts_css.exists():
        raw = fonts_css.read_bytes()
        gz = gzip.compress(raw, 6, mtime=0)
        print("D fonts.css 原始 %d B(%s),gzip-6 %d B(%s)"
              % (len(raw), kib(len(raw)), len(gz), kib(len(gz))))
    else:
        print("D fonts.css 不存在")
        return 1

    # E2. 批次 2 首页资产分型(磁盘;gzip 同 D 工具口径)
    # 3D 四件 gzip-6 ≤220KB;poster 两张合计 ≤450KB(首访仅传当前主题单张)
    td = SITE / "dist" / "3d"
    print("E2 首页 3D/poster 资产分型(dist/3d/,gzip-6 同 D 工具):")
    four = ("three.module.min.js", "three.core.min.js", "scene6.js", "boot6.js")
    raw_sum = gz_sum = 0
    missing = False
    for f in four:
        p = td / f
        if not p.exists():
            print("   缺失 %s" % f)
            missing = True
            continue
        raw = p.read_bytes()
        gz = gzip.compress(raw, 6, mtime=0)
        raw_sum += len(raw)
        gz_sum += len(gz)
        print("   %-20s 原始 %7d B  gzip-6 %7d B" % (f, len(raw), len(gz)))
    if not missing:
        print("   3D 四件合计 原始 %d B(%s),gzip-6 %d B(%s)≤220KB=%s"
              % (raw_sum, kib(raw_sum), gz_sum, kib(gz_sum),
                 "✓" if gz_sum <= 220 * 1024 else "✗"))
    posters = sorted(td.glob("poster-*.png"))
    p_raw = sum(p.stat().st_size for p in posters)
    for p in posters:
        print("   %-20s 原始 %7d B" % (p.name, p.stat().st_size))
    if len(posters) == 2:
        print("   poster 两张合计 %d B(%s)≤450KB(=450 KiB)=%s(首访单张)"
              % (p_raw, kib(p_raw),
                 "✓" if p_raw <= 450 * 1024 else "✗"))
    else:
        print("   poster 期望 2 张,实际 %d 张%s"
              % (len(posters),
                 "" if posters else "(未入库)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
