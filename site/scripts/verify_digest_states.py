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


def clear_persistent_store():
    """Astro 持久 data-store 经 node_modules junction 落在真实 site
    (node_modules/.astro),不清会残留夹具条目,之后空源(零期)的裸
    构建报「源文件数(0)与加载条目数不一致」。边界同
    clean-astro-cache.mjs:解析后不在本 site 内拒绝删除。"""
    target = SITE / "node_modules" / ".astro"
    if not target.exists():
        return True
    real = os.path.realpath(str(target))
    site_real = os.path.realpath(str(SITE))
    if real == site_real or not real.startswith(site_real + os.sep):
        print("[dstates] data-store 解析后不在本 site 内,拒绝删除:%s" % real)
        return False
    shutil.rmtree(real, ignore_errors=True)
    return not target.exists()


def build_with_digest(entries, tmp):
    """临时副本 + junction node_modules + 注入指定各期夹具,真实构建。
    entries = [(date, entry_count), ...]——多期用于「更新」态(旧期
    保留 + 新一期),断言期数派生与最新期跟随。"""
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
    for date, count in entries:
        raw = FIXTURE.read_text(encoding="utf-8")
        raw = raw.replace("date: '2026-10-04'", "date: '%s'" % date)
        raw = raw.replace("entry_count: 2", "entry_count: %d" % count)
        # 成本行内的引用与 frontmatter 无关,保留;文件名与 date 同步(id 惯例)
        (dig / ("%s.md" % date)).write_text(raw, encoding="utf-8")
    try:
        r = subprocess.run(
            ["node", "node_modules/astro/astro.js", "build"],
            cwd=str(tmp), capture_output=True, encoding="utf-8",
            errors="replace", shell=False)
    finally:
        # 无论成败都清 junction 落盘的持久 store,防残留污染真实构建
        clear_persistent_store()
    if r.returncode != 0:
        print(r.stdout[-800:], r.stderr[-800:])
        return False
    return True


def probe(pg, port, want_digest_json, want_li, want_blank, want_sub,
          want_latest=None):
    """加载首页,断言 data-digest/data-site/页面层状态/空态/面板名/
    订阅卡状态——同一份内容数据的派生口径(批次 C 文案轮:期数状态
    从 digests 派生,不用「存在」推导「每日一期」)。

    收口轮新增:实际展开「这个站 → AI 日报」层,层说明正文必须是稳定
    栏目介绍——含介绍、不含任何「暂无」空态宣称(是否已有/已发多少
    期由 li-state 与 digest 区动态表达,固定正文不复制状态判断);
    最新日报行/期数计数与状态派生同源(want_latest=None 为零期,
    (最新期日期, 期数) 为有期)。"""
    pg.goto("http://127.0.0.1:%d/" % port, wait_until="domcontentloaded")
    pg.click(".layer-item[data-layer=digest] .li-head")
    pg.wait_for_timeout(150)
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
                 || {textContent: ''}).textContent.trim(),
        tpDesc: (document.querySelector('#panel-digest .tp-desc')
                 || {textContent: ''}).textContent.trim(),
        sub: (document.querySelector(
              '.sub-cards .sub-card:nth-of-type(2) .sc-type')
              || {textContent: ''}).textContent.trim(),
        liBody: (document.querySelector(
                 '.layer-item[data-layer=digest] .li-body p')
                 || {textContent: ''}).textContent.trim(),
        rows: [...document.querySelectorAll(
          '.digest-empty .row-item h3')].map(x => x.textContent.trim()),
        digCount: (document.querySelector('.digest-empty .count')
                   || {textContent: ''}).textContent.trim(),
        bsState: (document.querySelector('.digest-empty .bs-state')
                  || {textContent: ''}).textContent.trim(),
        perDay: document.body.innerText.includes('每日一期')};}""")
    ds = dd = None
    try:
        ds = json.loads(st["ds"]) if st["ds"] else None
    except ValueError:
        pass
    try:
        dd = json.loads(st["dd"]) if st["dd"] else None
    except ValueError:
        pass
    # 层说明:稳定介绍可读,且不复制状态判断(任何态都不得宣称「暂无」)
    intro_ok = ("AI 自动生成的日报" in st["liBody"]
                and "暂无" not in st["liBody"])
    # 最新日报内容与期数状态同源
    if want_latest is None:
        latest_ok = (not st["rows"] and st["bsState"] == "暂无已发布日报"
                     and "AI 生成栏目" in st["digCount"])
    else:
        date, n = want_latest
        latest_ok = (len(st["rows"]) == n
                     and (date + " 日报") in st["rows"][0]
                     and st["digCount"].startswith("%d 期" % n))
    # 同源断言:data-site 的 digest 层 state == 页面 li-state 文本 ==
    # 订阅卡状态(同一份 digests 派生);全站不出现频次推导词
    dig_layer = (ds or [None, None, {}])[1] or {}
    ok = (isinstance(ds, list) and len(ds) == 3
          and dig_layer.get("state") == st["liText"]
          and st["liText"] == want_li
          and st["blank"] is want_blank
          and st["sub"] == want_sub
          and not st["perDay"]
          and intro_ok and latest_ok
          and (want_digest_json is None or dd == want_digest_json))
    return ok, {"dd": st["dd"], "li": st["liText"], "liCls": st["liClass"],
                "blank": st["blank"], "tp": st["tpName"],
                "tpDesc": st["tpDesc"][:24], "sub": st["sub"],
                "liBody": st["liBody"][:20], "rows": st["rows"][:2],
                "cnt": st["digCount"], "bs": st["bsState"][:8],
                "perDay": st["perDay"], "dsDig": dig_layer.get("state")}


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
            ok, d = probe(pg, PORT_BASE, None, "计划 · 暂无发布", True,
                          "AI 日报 · 暂无发布", None)
            check("dstates/zero", ok, str(d))
            httpd.shutdown()
            httpd = None

            # 态 2:有一期(date=2026-10-04,count=2)——状态从 digests
            # 派生为「已发 1 期」,不是「每日一期」频次推导
            if build_with_digest([("2026-10-04", 2)], tmp):
                httpd = serve(tmp / "dist", PORT_BASE + 1)
                ok, d = probe(pg, PORT_BASE + 1,
                              {"latest": {"date": "2026-10-04", "count": 2}},
                              "在线 · 已发 1 期", False,
                              "AI 日报 · 已发 1 期", ("2026-10-04", 1))
                check("dstates/one", ok and "2026-10-04" in d["tp"], str(d))
                httpd.shutdown()
                httpd = None
            else:
                check("dstates/one", False, "夹具构建失败")

            # 态 3:更新=旧期保留+新一期(2026-10-05)——期数派生 2 期,
            # 最新期跟随新值
            if build_with_digest([("2026-10-04", 2), ("2026-10-05", 5)], tmp):
                httpd = serve(tmp / "dist", PORT_BASE + 2)
                ok, d = probe(pg, PORT_BASE + 2,
                              {"latest": {"date": "2026-10-05", "count": 5}},
                              "在线 · 已发 2 期", False,
                              "AI 日报 · 已发 2 期", ("2026-10-05", 2))
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
        # 清理:先摘 junction 再删目录(顺序不可反);兜底再清一次经
        # junction 落盘的持久 store(build_with_digest 已按态清理,这里
        # 覆盖构建中途异常的路径)
        remove_junction(tmp / "node_modules")
        shutil.rmtree(tmp, ignore_errors=True)
        clear_persistent_store()

    fails = [l for l, ok in RESULTS if not ok]
    print("\n== %d/%d PASS ==" % (len(RESULTS) - len(fails), len(RESULTS)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
