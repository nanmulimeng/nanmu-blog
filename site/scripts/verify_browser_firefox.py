# -*- coding: utf-8 -*-
"""site 浏览器验收(Firefox,批次 3;入库可复跑)。

前置:npm run build(验收 dist/);本机 playwright + firefox。
用户批次 3 指令的 Firefox 面:内容、导航、主题、3D(正常+暂停)、
3D 降级(WebGL 禁用 pref)、reduced-motion。Chromium 才有的 CDP/
字体分片精细断言不在本文件;Chrome 版全量在 verify_browser.py。
降级模拟:launch(firefox_user_prefs={'webgl.disabled': True})——
pref 生效即无 WebGL 上下文,boot6 探测失败走 .no-webgl 终态。
浏览器版本随日志打印(观察项规程:提交 SHA+浏览器版本+完整输出)。
用法:python -I site/scripts/verify_browser_firefox.py [--port 8941]
"""
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_browser import poll_js, serve  # noqa: E402 同目录脚本(-I 不自动加)

PORT = 8941
SITE = Path(__file__).resolve().parents[1]  # site/

RESULTS = []


def check(label, ok, detail=""):
    RESULTS.append((label, ok))
    print("[%s] %s => %s" % (label, detail, "PASS" if ok else "FAIL"))


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 2 and sys.argv[1] == "--port":
        port = int(sys.argv[2])
    else:
        port = PORT
    httpd = serve(str(SITE / "dist"), port)
    base = "http://127.0.0.1:%d" % port
    try:
        with sync_playwright() as p:
            b = p.firefox.launch()
            print("firefox %s" % b.version)
            vp = {"viewport": {"width": 1440, "height": 900}}

            # ── A. 内容矩阵(昼):五页 + 404 关键元素 ──
            ctx = b.new_context(**vp)
            errs = []
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/posts/", wait_until="domcontentloaded")
            st = pg.evaluate("""() => ({
              rows: document.querySelectorAll('.row-item').length,
              blank: (document.querySelector('.blank-sheet .bs-state')
                      ||{textContent:''}).textContent})""")
            # 批次 C 撤稿:零文章空态,无文章行、不造假
            check("fx/posts", st["rows"] == 0 and "还没有文章" in st["blank"],
                  "rows=%d state=%s" % (st["rows"], st["blank"]))
            resp = pg.goto(base + "/posts/hello-nanmu-blog/",
                           wait_until="domcontentloaded")
            body = pg.evaluate("document.body.innerText")
            check("fx/post-withdrawn-404", resp.status == 404
                  and "你好" not in body[:200],
                  "status=%s" % resp.status)
            pg.goto(base + "/digest/", wait_until="domcontentloaded")
            st = pg.evaluate("""() => ({
              blank: !!document.querySelector('.blank-sheet .bs-state'),
              state: (document.querySelector('.blank-sheet .bs-state')
                      ||{textContent:''}).textContent})""")
            check("fx/digest", st["blank"] and "暂无" in st["state"],
                  "state=%s" % st["state"])
            pg.goto(base + "/about/", wait_until="domcontentloaded")
            st = pg.evaluate("""() => ({
              grid: !!document.querySelector('.about-grid'),
              facts: document.querySelectorAll('.fact-row').length})""")
            check("fx/about", st["grid"] and st["facts"] >= 2, str(st))
            pg.goto(base + "/", wait_until="domcontentloaded")
            st = pg.evaluate("""() => ({
              hero: !!document.querySelector('#scene3d'),
              posters: document.querySelectorAll('#scene3d img.poster').length,
              cover: !!document.querySelector('.cover-card'),
              tabs: document.querySelectorAll('.page-tabs button').length})""")
            # 批次 C 撤稿后零文章:页签目录在、无封面卡(空态不残留入口)
            check("fx/index", st["hero"] and st["posters"] >= 1
                  and not st["cover"] and st["tabs"] >= 3, str(st))
            pg.goto(base + "/404.html", wait_until="domcontentloaded")
            st = pg.evaluate("""() => ({
              h1: (document.querySelector('.gate-wrap h1')||{textContent:''}).textContent,
              links: document.querySelectorAll('.gate-links a').length})""")
            check("fx/404", st["h1"] != "" and st["links"] >= 1,
                  "h1=%s links=%d" % (st["h1"], st["links"]))
            check("fx/console", not errs, str(errs[:3]))
            pg.close()
            ctx.close()

            # ── B. 导航:链接数、点进文章、aria-current 跟随 ──
            ctx = b.new_context(**vp)
            pg = ctx.new_page()
            pg.goto(base + "/", wait_until="domcontentloaded")
            n = pg.evaluate("document.querySelectorAll('nav.main a').length")
            pg.click("nav.main a[href='/posts/']")
            pg.wait_for_function("location.pathname === '/posts/'",
                                 timeout=8000)
            cur = pg.evaluate("""(document.querySelector(
                "nav.main a[aria-current='page']")||{textContent:''})
                .textContent""")
            check("fx/nav", n >= 4 and "/posts/" in pg.url
                  and "文章" in cur, "links=%d cur=%s" % (n, cur))
            pg.close()
            ctx.close()

            # ── C. 主题三态:auto→light→dark,localStorage 持久 ──
            ctx = b.new_context(**vp)
            pg = ctx.new_page()
            pg.goto(base + "/posts/", wait_until="domcontentloaded")
            seq = []
            for _ in range(2):          # auto -> light -> dark
                pg.click("#theme-btn")
                pg.wait_for_timeout(150)
                seq.append(pg.evaluate(
                    "document.documentElement.dataset.theme || 'auto'"))
            ls = pg.evaluate(
                "try{localStorage.getItem('nm-theme')}catch(e){null}")
            pg.goto(base + "/posts/", wait_until="domcontentloaded")
            keep = pg.evaluate(
                "document.documentElement.dataset.theme || 'auto'")
            bg = pg.evaluate(
                "getComputedStyle(document.body).backgroundColor")
            check("fx/theme", seq == ["light", "dark"] and ls == "dark"
                  and keep == "dark" and bg != "rgb(240, 237, 229)",
                  "seq=%s ls=%s keep=%s bg=%s" % (seq, ls, keep, bg))
            pg.close()
            ctx.close()

            # ── D. 3D:boot 就绪、页签↔场景联动、暂停组合 ──
            ctx = b.new_context(**vp)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(base + "/", wait_until="domcontentloaded")
            boot = poll_js(pg, "!!window.__bookscene"
                           " && document.querySelectorAll('#scene3d img.poster')"
                           ".length === 0", 30000)
            st = pg.evaluate("""(() => {
              const s = window.__bookscene;
              if (!s) return {boot: false};
              return {boot: true, tris: s.stats().triangles};})()""")
            check("fx3d/boot", bool(boot) and st.get("boot")
                  and st.get("tris", 0) > 0,
                  "boot=%s tris=%s" % (bool(boot), st.get("tris")))
            if not boot:
                for lbl in ("fx3d/tab-link", "fx3d/pause-combo"):
                    check(lbl, False, "无 __bookscene(3D 未就绪)")
            else:
                pg.click("#tab-digest")
                cur = poll_js(pg, "window.__bookscene"
                              " && window.__bookscene.current() === 'digest'",
                              6000)
                check("fx3d/tab-link", bool(cur), "current=%s"
                      % pg.evaluate("window.__bookscene.current()"))
                # 暂停→选择→拖拽→resize→复位→恢复(needsLoop 即时重绘)
                pg.evaluate("window.__bookscene.setAmbient(false)")
                pg.evaluate("window.__bookscene.select('about')")
                curOk = poll_js(pg, "window.__bookscene"
                                ".current() === 'about'", 8000)
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
                  return {amb: s.isAmbientOn(), cur: s.current(),
                          tris: s.stats().triangles};})()""")
                check("fx3d/pause-combo", curOk and st2["amb"] is True
                      and st2["cur"] == "about" and st2["tris"] > 0
                      and not errs,
                      "cur=%s amb=%s tris=%s errs=%s"
                      % (st2["cur"], st2["amb"], st2["tris"], errs[:2]))
            pg.close()
            ctx.close()

            # ── E. 3D 降级:webgl.disabled pref → no-webgl + poster 常显 ──
            b2 = p.firefox.launch(firefox_user_prefs={"webgl.disabled": True})
            try:
                ctx = b2.new_context(**vp)
                pg = ctx.new_page()
                reqs = []
                pg.on("request", lambda r: reqs.append(r.url))
                errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                pg.goto(base + "/", wait_until="domcontentloaded")
                pg.wait_for_timeout(3000)
                st = pg.evaluate("""() => ({
                  noWebgl: (document.querySelector('#scene3d')
                      || {classList: {contains: () => false}})
                      .classList.contains('no-webgl'),
                  posters: document.querySelectorAll('#scene3d img.poster').length,
                  hud: !!document.querySelector('.scene-hud')})""")
                pg.click("#tab-digest", timeout=3000)
                pg.wait_for_timeout(300)
                tabok = pg.evaluate(
                    "!(document.getElementById('panel-digest')"
                    " || {hasAttribute: () => true}).hasAttribute('hidden')")
                three = [u for u in reqs if "/3d/" in u
                         and "poster" not in u and "boot6" not in u]
                check("fx3d/no-webgl", st["noWebgl"] and st["posters"] >= 1
                      and not st["hud"] and tabok and not three and not errs,
                      "no-webgl=%s posters=%d hud=%s tab=%s 3d=%d errs=%s"
                      % (st["noWebgl"], st["posters"], st["hud"], tabok,
                         len(three), errs[:2]))
                pg.close()
                ctx.close()
            except Exception as exc:  # noqa: BLE001 验收脚本:缺失即 FAIL
                check("fx3d/no-webgl", False, str(exc)[:80])
            b2.close()

            # ── F. reduced-motion:过渡归零、404 静止 ──
            ctx = b.new_context(reduced_motion="reduce", **vp)
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
            pg.goto(base + "/404.html", wait_until="domcontentloaded")
            anim = pg.evaluate("""() => {
              const lift = document.querySelector('.gate .lift');
              return lift ? getComputedStyle(lift).animationName
                          : 'missing';}""")
            check("fx/reduced", st["sb"] == "auto" and dur < 0.001
                  and anim == "none",
                  "scroll=%s dur=%s anim=%s" % (st["sb"], st["td"], anim))
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
