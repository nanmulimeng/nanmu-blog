# -*- coding: utf-8 -*-
"""日报状态与站点说明同源验收(三态构建,批次 3 收尾入库)。

修正轮反例 r6-f3 的可复跑版:日报零期/一期/更新三态下,页面层列表
li-state、#scene3d 的 data-digest/data-site、页签面板最新期名是否
同源跟随(3D 纹理与页面层共用同一构建期派生,改一处即不同步)。

三态:
  1 零日报 = 现场 dist(前置:npm run build 已跑);
  2 一期   = 临时站点副本 + tests/fixtures 夹具(date/entry_count 改写)
             经真实 astro build(与 verify-fixture.mjs 同口径:
             node_modules 以 junction 复用,不复制);
  3 更新   = 改夹具 date/entry_count 再建,断言 data-digest 跟随新值。

用法:python -I site/scripts/verify_digest_states.py
(前置 site/dist 为最新构建;态 2/3 额外各做一次临时构建,共 ~1 分钟)
"""
import http.server
import json
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
FIXTURE = SITE / "tests" / "fixtures" / "2026-10-04.md"
CHROME = find_chrome()
PORT_BASE = 8971
RESULTS = []


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
    """摘 node_modules 链接本身;未确认摘除前绝不 rmtree(会穿过链接
    递归删真实 node_modules)。返回是否已不在。"""
    if not link.exists():
        return True
    try:
        os.rmdir(link)          # Windows junction:只删链接本身
    except OSError:
        try:
            link.unlink()       # POSIX symlink
        except OSError:
            return False
    return not link.exists()


def build_with_digest(date, count, tmp):
    """临时副本 + junction node_modules + 注入指定日期/条数的夹具,真实构建。"""
    if tmp.exists():
        if not remove_junction(tmp / "node_modules"):
            raise RuntimeError("旧 junction 无法摘除,拒绝继续(保护真实"
                               " node_modules)")
        shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(SITE, tmp, ignore=shutil.ignore_patterns(
        "node_modules", "dist", ".astro"))
    link = tmp / "node_modules"
    try:
        import _winapi
        _winapi.CreateJunction(str(SITE / "node_modules"), str(link))
    except (ImportError, OSError):
        os.symlink(str(SITE / "node_modules"), str(link))  # POSIX 退符号链接
    dig = tmp / "src" / "content" / "digest"
    dig.mkdir(parents=True, exist_ok=True)
    raw = FIXTURE.read_text(encoding="utf-8")
    raw = raw.replace("date: '2026-10-04'", "date: '%s'" % date)
    raw = raw.replace("entry_count: 2", "entry_count: %d" % count)
    # 成本行内的引用与 frontmatter 无关,保留;文件名与 date 同步(id 惯例)
    (dig / ("%s.md" % date)).write_text(raw, encoding="utf-8")
    r = subprocess.run(
        ["node", "node_modules/astro/astro.js", "build"],
        cwd=str(tmp), capture_output=True, encoding="utf-8",
        errors="replace", shell=False)
    if r.returncode != 0:
        print(r.stdout[-800:], r.stderr[-800:])
        return False
    return True


def probe(pg, port, want_digest_json, want_li, want_blank):
    """加载首页,断言 data-digest/data-site/页面层状态/空态/面板名。"""
    pg.goto("http://127.0.0.1:%d/" % port, wait_until="domcontentloaded")
    st = pg.evaluate("""() => {
      const host = document.querySelector('#scene3d');
      const li = document.querySelector(
        '.layer-item[data-layer=digest] .li-state');
      return {
        dd: host ? host.getAttribute('data-digest') : '(no-host)',
        ds: host ? host.getAttribute('data-site') : null,
        liText: li ? li.textContent.trim() : '(no-li)',
        liClass: li ? li.className : '',
        blank: !!document.querySelector('.digest-empty .bs-state'),
        tpName: (document.querySelector('#panel-digest .tp-name')
                 || {textContent: ''}).textContent.trim()};}""")
    ds = dd = None
    try:
        ds = json.loads(st["ds"]) if st["ds"] else None
    except ValueError:
        pass
    try:
        dd = json.loads(st["dd"]) if st["dd"] else None
    except ValueError:
        pass
    # 同源断言:data-site 的 digest 层 state == 页面 li-state 文本
    dig_layer = (ds or [None, None, {}])[1] or {}
    ok = (isinstance(ds, list) and len(ds) == 3
          and dig_layer.get("state") == st["liText"]
          and st["liText"] == want_li
          and st["blank"] is want_blank
          and (want_digest_json is None or dd == want_digest_json))
    return ok, {"dd": st["dd"], "li": st["liText"], "liCls": st["liClass"],
                "blank": st["blank"], "tp": st["tpName"],
                "dsDig": dig_layer.get("state")}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not (SITE / "dist" / "index.html").exists():
        print("前置缺失:先 npm run build(态 1 用现场 dist)")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="nanmu-dstates-"))
    httpd = None
    try:
        with sync_playwright() as p:
            launch = ({"executable_path": CHROME} if CHROME else {})
            b = p.chromium.launch(**launch)
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            pg = ctx.new_page()

            # 态 1:零日报(现场 dist;data-digest 空串断言在
            # verify_browser.py I 段固化,这里不断言 dd 值)
            httpd = serve(SITE / "dist", PORT_BASE)
            ok, d = probe(pg, PORT_BASE, None, "计划 · 引擎评审通过", True)
            check("dstates/zero", ok, str(d))
            httpd.shutdown()
            httpd = None

            # 态 2:有一期(date=2026-10-04,count=2)
            if build_with_digest("2026-10-04", 2, tmp):
                httpd = serve(tmp / "dist", PORT_BASE + 1)
                ok, d = probe(pg, PORT_BASE + 1,
                              {"latest": {"date": "2026-10-04", "count": 2}},
                              "在线 · 每日一期", False)
                check("dstates/one", ok and "2026-10-04" in d["tp"], str(d))
                httpd.shutdown()
                httpd = None
            else:
                check("dstates/one", False, "夹具构建失败")

            # 态 3:更新(date=2026-10-05,count=5)
            if build_with_digest("2026-10-05", 5, tmp):
                httpd = serve(tmp / "dist", PORT_BASE + 2)
                ok, d = probe(pg, PORT_BASE + 2,
                              {"latest": {"date": "2026-10-05", "count": 5}},
                              "在线 · 每日一期", False)
                check("dstates/updated", ok and "2026-10-05" in d["tp"],
                      str(d))
                httpd.shutdown()
                httpd = None
            else:
                check("dstates/updated", False, "夹具构建失败")

            pg.close()
            ctx.close()
            b.close()
    finally:
        if httpd:
            httpd.shutdown()
        # 清理:先摘 junction 再删目录(顺序不可反)
        remove_junction(tmp / "node_modules")
        shutil.rmtree(tmp, ignore_errors=True)

    fails = [l for l, ok in RESULTS if not ok]
    print("\n== %d/%d PASS ==" % (len(RESULTS) - len(fails), len(RESULTS)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
