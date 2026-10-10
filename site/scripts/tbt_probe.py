# -*- coding: utf-8 -*-
"""批次 3 修正轮:同移动节流「正常 3D / 静态首页」操作响应对照。

口径:CDP 真节流 = 4×CPU + RTT 150ms + 1.6Mbps 下行(与批次 3
Lighthouse 移动档同条件);390×844 移动视口。两组各跑一轮:
  full   —— 正常首页(3D idle 动态加载 + 场景构建)
  static —— abort scene6/three(boot6 探测保留,模块不可得走失败
            清理,poster 常显 =「无 3D 的静态首页」;与批次 2 的
            scene6-abort 终态验收同一路径)
场景初始化窗口(t≈7-14s)内每 2s 一轮真实点击:目录开合 / 页签
切换 / 阅读入口(探针 preventDefault,不真跳转);capture click +
requestAnimationFrame 记「输入→下一帧」延迟;PerformanceObserver
记 longtask 与 LCP 候选;FCP 自 paint 条目。
产出:logs/r6-b3-tbt-compare-{full,static}.json + stdout 摘要。
一次性补证工具,无 PASS/FAIL 断言:数据供性能取舍裁决,不自动优化。
用法:python -I scripts/tbt_probe.py [--port 8944](前置 npm run build)
"""
import json
import statistics
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_browser import find_chrome, serve  # noqa: E402 同目录(-I)

PORT = 8944
SITE = Path(__file__).resolve().parents[1]          # site/
LOGS = (SITE.parent / "docs" / "design" / "2026-10-07-visual-redesign"
        / "logs")                                    # 历轮 r6-b3-* 归档处
ROUNDS_AT = (7, 9, 11, 13)                          # 场景窗口内墙钟秒

PROBE_JS = """
(() => {
  window.__probe = {ops: [], longtasks: [], lcp: [], fcp: -1};
  new PerformanceObserver(list => {
    for (const e of list.getEntries())
      window.__probe.longtasks.push(
        {start: Math.round(e.startTime), dur: Math.round(e.duration),
         name: ((e.attribution || [])[0] || {}).name || ''});
  }).observe({entryTypes: ['longtask']});
  new PerformanceObserver(list => {
    const es = list.getEntries();
    if (es.length) window.__probe.lcp = es.map(e => (
      {start: Math.round(e.startTime), size: e.size,
       url: e.url || '', tag: e.element ? e.element.tagName : ''}));
  }).observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver(list => {
    for (const e of list.getEntries())
      if (e.name === 'first-contentful-paint')
        window.__probe.fcp = Math.round(e.startTime);
  }).observe({type: 'paint', buffered: true});
  document.addEventListener('click', e => {
    if (!e.target.closest) return;
    const read = e.target.closest('.btn.primary');
    if (read) e.preventDefault();          // 阅读入口只测响应,不真跳转
    const what = e.target.closest('.menu-toggle') ? 'menu'
        : e.target.closest('.page-tabs button') ? 'tab'
        : read ? 'read' : 'other';
    if (what === 'other') return;
    const t0 = performance.now();
    requestAnimationFrame(() => {
      window.__probe.ops.push(
        {t: Math.round(t0), dt: Math.round(performance.now() - t0),
         what: what});
    });
  }, true);
})();
"""


def run_group(b, base, mode):
    ctx = b.new_context(viewport={"width": 390, "height": 844},
                        has_touch=True, is_mobile=True)
    pg = ctx.new_page()
    if mode == "static":
        pg.route("**/3d/scene6*", lambda r: r.abort())
        pg.route("**/3d/three*", lambda r: r.abort())
    cdp = ctx.new_cdp_session(pg)
    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    cdp.send("Network.emulateNetworkConditions",
             {"offline": False, "latency": 150,
              "downloadThroughput": 200000,   # 1.6Mbps
              "uploadThroughput": 93750})
    pg.add_init_script(PROBE_JS)
    reqs = []
    pg.on("request", lambda r: reqs.append(r.url))
    t0 = time.time()
    pg.goto(base + "/", wait_until="domcontentloaded")

    def at(sec):
        """睡到墙钟第 sec 秒,再执行一轮三入口点击。"""
        remain = t0 + sec - time.time()
        if remain > 0:
            pg.wait_for_timeout(remain * 1000)
        pg.click(".menu-toggle")             # 目录:开
        pg.wait_for_timeout(300)
        pg.click(".menu-toggle")             # 目录:关
        pg.click("#tab-digest")              # 页签:posts→digest
        pg.wait_for_timeout(500)
        pg.click("#tab-posts")               # 页签:digest→posts
        pg.click(".btn.primary")             # 阅读入口(preventDefault)

    for sec in ROUNDS_AT:
        at(sec)
    pg.wait_for_timeout(2000)

    data = pg.evaluate("window.__probe")
    data["sceneReady"] = pg.evaluate(
        "!!window.__bookscene")
    data["posterGone"] = pg.evaluate(
        "document.querySelectorAll('#scene3d img.poster').length === 0")
    data["tRun"] = round(time.time() - t0, 1)
    data["threeReqs"] = sorted(u for u in reqs if "/3d/" in u
                               and "poster" not in u)
    pg.close()
    ctx.close()
    return data


def summarize(mode, d):
    print("[%s] run=%.1fs scene=%s posterGone=%s fcp=%dms lcp=%dms(%s)"
          % (mode, d["tRun"], d["sceneReady"], d["posterGone"],
             d["fcp"],
             d["lcp"][-1]["start"] if d["lcp"] else -1,
             (d["lcp"][-1]["tag"] or d["lcp"][-1]["url"] or "?")
             if d["lcp"] else "?"))
    lts = d["longtasks"]
    print("[%s] longtasks=%d Σdur=%dms"
          % (mode, len(lts), sum(x["dur"] for x in lts)))
    for x in lts:
        print("[%s]   longtask start=%dms dur=%dms %s"
              % (mode, x["start"], x["dur"], x["name"]))
    for what in ("menu", "tab", "read"):
        dts = [o["dt"] for o in d["ops"] if o["what"] == what]
        if dts:
            print("[%s] ops/%s n=%d min=%d med=%d max=%d ms"
                  % (mode, what, len(dts), min(dts),
                     statistics.median(dts), max(dts)))
            print("[%s]   dts=%s" % (mode, dts))
        else:
            print("[%s] ops/%s n=0(未捕获)" % (mode, what))


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
            launch = ({"executable_path": find_chrome()}
                      if find_chrome() else {})
            b = p.chromium.launch(**launch)
            print("chromium %s" % b.version)
            for mode in ("full", "static"):
                d = run_group(b, base, mode)
                summarize(mode, d)
                out = LOGS / ("r6-b3-tbt-compare-%s.json" % mode)
                out.write_text(json.dumps(d, ensure_ascii=False,
                                          indent=1), encoding="utf-8")
                print("[%s] saved %s" % (mode, out))
            b.close()
    finally:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
