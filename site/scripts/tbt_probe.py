# -*- coding: utf-8 -*-
"""批次 3 测量修正轮(v2):同条件「正常 3D / 静态首页」输入延迟对照。

v1 勘误(2026-10-10 用户审计):v1 探针在 click 处理函数内起测
(performance.now() 于 handler 首行 + rAF),只覆盖「处理开始→下一帧」,
遗漏输入排队延迟(startTime→processingStart)——「操作响应两组无差异/
交互可用性已证无影响」结论撤回,痕迹保留在 v1 日志与
2026-10-10-r6-batch03-tbt-remeasure.md。

v2 口径(条件与 logs/r6-b3-lh-after-*.excerpt.json 归档配置逐项对齐):
  - 交互计时 = Event Timing(PerformanceEventTiming):每交互记
    startTime / processingStart / processingEnd / duration /
    interactionId,派生 inputDelay(输入排队)/ processing(事件处理)/
    presentation(绘制等待 = duration - (processingEnd - startTime));
    durationThreshold=16(Chromium 下限)以覆盖快交互;
    **未收到条目登记为 missing,不填 0**。
  - 点击 = mouse.click 坐标 = CDP Input 真实输入(浏览器进程合成,
    渲染线程忙则入队排队);不用 pg.click 的 actionability 自动等待
    ——那会等渲染线程空闲,恰好掩盖要测的阻塞。
  - **async 并发派发(仪器自检 R2 勘误的同一机理)**:sync API 的
    mouse.click 等 CDP ack,而 Input ack 要等渲染线程空闲——串行
    await 会把后续点击推迟到长任务结束后才上线,排队被整个掩盖
    (自检实测 target.timeStamp 落在阻塞后)。因此:每轮开始预取
    全部入口坐标,轮内每击 create_task 派发后不等 ack、间隔用纯
    墙钟 asyncio.sleep,轮末 gather 收尾;dispatch 命令按序上线,
    长任务期间的输入真实入队。自检证据(独立测试页,不混入本数据):
    logs/r6-b3-eventtiming-selfcheck.log,6/6 PASS(含 v1 口径失明
    对照)。
  - 视口 412×823 / DSF1.75 / is_mobile(= 归档 screenEmulation);
    节流 latency=562.5ms / 下行 184320 B/s / 上行 84375 B/s / CPU 4×
    (= 归档 throttling:requestLatencyMs 562.5、1474.56/675 kbps,
    cpuSlowdownMultiplier 4;v1 误用 RTT150/1.6Mbps 属独立条件,已勘误)。
  - 服务:内置 gzip-6 静态服务(text 类压缩、woff2/png 跳过,同 8982
    规则),full/static 两组共用同一实例 = 服务/压缩/视口/节流一致。
  - 采样阶段:P1 加载与场景窗口(t≈6s 起,每 ~2s 一轮三入口点击)→
    P2 等待 poster 退场(持续采样)→ P3 poster 退场后稳定期 3 轮;
    统一观察窗 20s(两组一致:full 早收口记 p3-stable,static poster
    常显为 abort 路径预期终态、窗口截止记 window,不再跑满 45s);
    sceneReady/posterGone 未在窗口内达成 = 如实登记超时。
  - 重叠判定:交互条目的 [startTime, processingStart) 与任一 longtask
    区间相交 = 排队受长任务影响的实际样本(overlap),逐条列出。
产出:logs/r6-b3-tbt3-compare-{full,static}.json + stdout 摘要
(tbt2=2026-10-10 v2 重测基线;tbt3=2026-10-13 口径修正+B 优化后对照)。
一次性补证工具,无 PASS/FAIL 断言:数据供性能取舍裁决,不自动优化。
用法:python -I scripts/tbt_probe.py [--port 8945](前置 npm run build)
"""
import asyncio
import gzip
import http.server
import json
import statistics
import sys
import threading
import time
from functools import partial
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_browser import find_chrome  # noqa: E402 同目录(-I)

PORT = 8945
SITE = Path(__file__).resolve().parents[1]          # site/
LOGS = (SITE.parent / "docs" / "design" / "2026-10-07-visual-redesign"
        / "logs")                                    # 历轮 r6-b3-* 归档处
DEADLINE_S = 45.0                                    # (已废,见 MAX_WINDOW_S)
MAX_WINDOW_S = 20.0                                  # 统一观察窗:两组一致收口,
                                                     # static poster 常显按预期
                                                     # 终态处理,不再跑满 45s
ROUND_GAP_S = 1.0                                    # 轮间隔(v2.1 加密,见 OPS 注)
P1_FROM_S = 6.0                                      # 首轮墙钟秒
P3_ROUNDS = 3                                        # poster 退场后稳定轮数
LH_TBT_HOME_MS = 846.4   # 引用自归档摘录 r6-b3-lh-after-home.excerpt.json

# Event Timing 探针(仪器自检脚本与本探针共用同一段:上项目的仪器
# 就是自检过的仪器)。
EVENT_TIMING_JS = """
(() => {
  window.__ev = [];
  new PerformanceObserver(list => {
    for (const e of list.getEntries()) {
      window.__ev.push({
        name: e.name, start: e.startTime,
        pStart: e.processingStart, pEnd: e.processingEnd,
        dur: e.duration, iid: e.interactionId});
    }
  }).observe({type: 'event', durationThreshold: 16, buffered: true});
})();
"""

LONGTASK_JS = """
(() => {
  window.__lt = [];
  new PerformanceObserver(list => {
    for (const e of list.getEntries())
      window.__lt.push(
        {start: e.startTime, dur: e.duration,
         name: ((e.attribution || [])[0] || {}).name || ''});
  }).observe({entryTypes: ['longtask'], buffered: true});
})();
"""

# 项目页专属:入口分类 + 阅读入口 preventDefault(不真跳转)。
# 不再在 handler 内计时(v1 缺陷)——计时全部交给 Event Timing。
PAGE_HOOK_JS = """
(() => {
  window.__clicks = [];
  document.addEventListener('click', e => {
    if (!e.target.closest) return;
    const read = e.target.closest('.btn.primary');
    if (read) e.preventDefault();
    const what = e.target.closest('.menu-toggle') ? 'menu'
        : e.target.closest('.page-tabs button') ? 'tab'
        : read ? 'read' : 'other';
    if (what === 'other') return;
    window.__clicks.push({t: e.timeStamp, what: what});
  }, true);
  new PerformanceObserver(list => {
    const es = list.getEntries();
    if (es.length) window.__lcp = es.map(e => (
      {start: Math.round(e.startTime), size: e.size,
       url: e.url || '', tag: e.element ? e.element.tagName : ''}));
  }).observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver(list => {
    for (const e of list.getEntries())
      if (e.name === 'first-contentful-paint')
        window.__fcp = Math.round(e.startTime);
  }).observe({type: 'paint', buffered: true});
})();
"""

PROBE_JS = EVENT_TIMING_JS + LONGTASK_JS + PAGE_HOOK_JS

OPS = (("menu", ".menu-toggle", 150),     # 目录:开 → 间隔 → 关
       ("menu", ".menu-toggle", 175),
       ("tab", "#tab-digest", 250),       # 页签:posts→digest → 间隔 → 回
       ("tab", "#tab-posts", 250),
       ("read", ".btn.primary", 0))       # 阅读入口(preventDefault)
# 击点节拍演进:v2.0(gap 300/350/500/500、轮距 2s)125 次 hook 点击
# 无一落入长任务窗口(最近 242ms)——「未采到」而非「无阻塞」;
# v2.1 加密至 150/175/250/250 + 轮距 1s 仍 overlap=0,数据显示点击
# 序列在长任务两侧出现 ~0.9s 空隙 = 轮内协议往返(read 的 query/box、
# 轮末 gather 等 ack)在渲染线程忙时挂起,把击点弹开到窗口之外;
# v2.2 = read 坐标并入轮前预取(滚动取盒滚回)+ 击任务 fire-and-
# forget 跨轮累积不 gather。仪器/服务/节流/视口均不变。


class GzipHandler(http.server.SimpleHTTPRequestHandler):
    """text 类 gzip-6(同 8982 规则);woff2/png 直传;no-store 冷载。"""

    def do_GET(self):
        # 状态行必须先于任何 header 写入(首版在 else 分支先
        # send_header 再 super().do_GET,headers buffer 顺序颠倒,
        # 响应非法 → net::ERR_INVALID_HTTP_RESPONSE,已勘误)。
        # text 判定按实际文件后缀(目录请求 `/` 已映射 index.html,
        # self.path.endswith 会漏掉它 → 首页 HTML 未压缩直传,已勘误)。
        p = Path(self.translate_path(self.path))
        if p.is_dir():
            p = p / "index.html"
        if p.is_file():
            text = p.suffix in (".html", ".css", ".js", ".json",
                                ".svg", ".txt", ".xml")
            body = (gzip.compress(p.read_bytes(), 6, mtime=0) if text
                    else p.read_bytes())
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(str(p)))
            if text:
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *a):              # 静默访问日志
        pass


def serve_gzip(root, port):
    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", port), partial(GzipHandler, directory=root))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def prefetch_boxes(pg):
    """轮开始时一次性预取各入口盒子(此时渲染线程大概率空闲,协议
    往返不会被长任务挂起);轮内点击只发 Input,不做任何查询往返。"""
    boxes = {}
    for what, sel, gap in OPS:
        el = await pg.query_selector(sel)
        boxes[sel] = await el.bounding_box() if el else None
    return boxes


async def dispatch_click(pg, sel, what, boxes, dispatch_log):
    """真实输入点击(预取坐标中心)。

    不可见/缺盒登记 skipped 不静默丢弃;tMs = 该击 ack 完成墙钟
    (过程记录;输入的真实时刻以 Event Timing startTime 为准)。
    """
    box = boxes.get(sel)
    if not box or box["width"] <= 0:
        dispatch_log.append({"what": what, "skipped": "no-box"})
        return
    await pg.mouse.click(box["x"] + box["width"] / 2,
                         box["y"] + box["height"] / 2)
    dispatch_log.append({"what": what, "tMs": round(time.time() * 1000)})


async def dispatch_read(pg, what, box, dispatch_log):
    """阅读入口:按钮在首屏之外(412×823 下中心 y≈933 > 视口)。

    mouse.click 视口外坐标不产生页面事件(两轮勘误:滚动后取盒
    与轮内取盒的往返都会被长任务挂起/错位)。v2.2 定稿 = 三连纯
    Input:wheel 滚 200px → click(顶位坐标 y−200 = 滚动后视口
    位置;按钮非 sticky,换算成立)→ wheel 滚回。零协议往返,
    renderer 忙时三动作同队保序(wheel 处理完滚动,click 落在新
    位置)。
    """
    if not box or box["width"] <= 0:
        dispatch_log.append({"what": what, "skipped": "no-box"})
        return
    await pg.mouse.wheel(0, 200)
    await asyncio.sleep(0.05)                # 墙钟微间隔(保序即可)
    await pg.mouse.click(box["x"] + box["width"] / 2,
                         box["y"] + box["height"] / 2 - 200)
    await pg.mouse.wheel(0, -200)
    dispatch_log.append({"what": what, "tMs": round(time.time() * 1000)})


async def collect(pg):
    return await pg.evaluate(
        "({events: window.__ev || [], longtasks: window.__lt || [],"
        " clicks: window.__clicks || [], lcp: window.__lcp || [],"
        " fcp: (window.__fcp === undefined ? -1 : window.__fcp)})")


async def run_group(b, base, mode):
    ctx = await b.new_context(viewport={"width": 412, "height": 823},
                              device_scale_factor=1.75,
                              has_touch=True, is_mobile=True)
    pg = await ctx.new_page()
    if mode == "static":
        await pg.route("**/3d/scene6*", lambda r: r.abort())
        await pg.route("**/3d/three*", lambda r: r.abort())
    cdp = await ctx.new_cdp_session(pg)
    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
    # 归档 throttling 实参(requestLatencyMs 562.5 / 1474.56 / 675 kbps)
    await cdp.send("Network.emulateNetworkConditions",
                   {"offline": False, "latency": 562.5,
                    "downloadThroughput": 184320,
                    "uploadThroughput": 84375})
    await pg.add_init_script(PROBE_JS)
    reqs = []
    pg.on("request", lambda r: reqs.append(r.url))
    t0 = time.time()
    await pg.goto(base + "/", wait_until="domcontentloaded")

    dispatch_log = []
    round_marks = []                             # 每轮墙钟偏移秒
    scene_at = poster_at = None
    stop_reason = "window"                       # p3-stable | window
    pending = []                                 # 击任务跨轮累积(见下)

    async def poll_states():
        nonlocal scene_at, poster_at
        now = time.time() - t0
        if scene_at is None and await pg.evaluate("!!window.__bookscene"):
            scene_at = now
        if poster_at is None and await pg.evaluate(
                "document.querySelectorAll('#scene3d img.poster')"
                ".length === 0"):
            poster_at = now

    while True:
        now = time.time() - t0
        # 统一观察窗(两组一致):poster 退场+P3 稳定轮早收口,否则
        # 20s 窗口截止——static 组 poster 常显是 abort 路径的预期终态,
        # 不再为等它跑满 45s(截止原因如实登记 stopReason)
        if now >= MAX_WINDOW_S:
            stop_reason = "window"
            break
        if now >= P1_FROM_S and now - (round_marks[-1] if round_marks
                                       else P1_FROM_S - ROUND_GAP_S) \
                >= ROUND_GAP_S:
            round_marks.append(now)
            boxes = await prefetch_boxes(pg)
            for what, sel, gap in OPS:
                # 击任务 fire-and-forget:命令上线即返回控制,不等
                # ack——长任务期间后续击照常上线入队(自检 R2 勘误
                # 同一机理);不 gather 等待,避免某击 ack 挂起把
                # 下一轮整体弹开到长任务窗口之外。间隔纯墙钟,
                # dispatch 顺序 = OPS 顺序。
                pending.append(asyncio.create_task(
                    (dispatch_read(pg, what, boxes.get(".btn.primary"),
                                   dispatch_log)
                     if what == "read" else
                     dispatch_click(pg, sel, what, boxes, dispatch_log))))
                await asyncio.sleep(gap / 1000.0)
            await poll_states()
            # P3:poster 已退场且其后已采满稳定轮 → 收口
            if poster_at is not None and sum(
                    1 for r in round_marks if r > poster_at) >= P3_ROUNDS:
                stop_reason = "p3-stable"
                break
            continue
        await poll_states()
        await asyncio.sleep(0.2)         # 纯墙钟等待,无协议往返

    # 收尾前收割全部击任务(ack 迟早返回;异常不中断采集)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    data = await collect(pg)
    data.update({
        "mode": mode, "tRun": round(time.time() - t0, 1),
        "sceneAt": round(scene_at, 1) if scene_at is not None else None,
        "posterAt": round(poster_at, 1) if poster_at is not None else None,
        "sceneTimeout": scene_at is None,
        "posterTimeout": poster_at is None,
        "stopReason": stop_reason,
        "nRounds": len(round_marks),
        "dispatch": dispatch_log,
        "threeReqs": sorted(u for u in reqs if "/3d/" in u
                            and "poster" not in u),
        "config": {
            "viewport": "412x823 DSF1.75 is_mobile",
            "throttle": ("latency=562.5ms down=184320B/s up=84375B/s"
                         " cpu=4x (=archived throttling)"),
            "service": "builtin gzip-6 (text only), no-store, shared",
            "windowS": MAX_WINDOW_S,
            "click": ("CDP Input via mouse.click, async create_task"
                      " dispatch (no ack serialization, no"
                      " actionability wait)"),
            "lhTbtHomeMs": LH_TBT_HOME_MS,
            # static 组 Lighthouse 未测:归档摘录仅 full 首页一组
            "lhTbtStatic": "not-measured"},
    })
    await pg.close()
    await ctx.close()
    return data


def pair_clicks(data):
    """__clicks(hook)× __ev(Event Timing click 条目)按 startTime 配对。

    e.timeStamp 与 PerformanceEventTiming.startTime 同源同值;±5ms 容差
    兜同名并发。未配上 = missing(不填 0)。重叠 = inputDelay 区间
    [start, processingStart) 与任一 longtask [start, start+dur) 相交。
    """
    lts = data["longtasks"]
    for c in data["clicks"]:
        cands = [e for e in data["events"]
                 if e["name"] == "click" and abs(e["start"] - c["t"]) <= 5]
        if not cands:
            c["paired"] = False
            continue
        e = min(cands, key=lambda x: abs(x["start"] - c["t"]))
        c["paired"] = True
        c["start"] = round(e["start"], 1)
        c["inputDelay"] = round(e["pStart"] - e["start"], 1)
        c["processing"] = round(e["pEnd"] - e["pStart"], 1)
        c["presentation"] = round(e["dur"] - (e["pEnd"] - e["start"]), 1)
        c["durTotal"] = round(e["dur"], 1)
        c["iid"] = e["iid"]
        ov = [lt for lt in lts
              if e["start"] < lt["start"] + lt["dur"]
              and e["pStart"] > lt["start"]]
        c["overlap"] = [{"start": round(lt["start"]),
                         "dur": round(lt["dur"])} for lt in ov]
    return data


def dist(vals):
    if not vals:
        return "n=0"
    return "n=%d min=%.0f med=%.0f max=%.0f ms" % (
        len(vals), min(vals), statistics.median(vals), max(vals))


def summarize(mode, d):
    print("[%s] tRun=%.1fs rounds=%d stopReason=%s scene@%s poster@%s"
          " sceneTimeout=%s posterTimeout=%s%s"
          % (mode, d["tRun"], d["nRounds"], d.get("stopReason", "?"),
             d["sceneAt"], d["posterAt"],
             d["sceneTimeout"], d["posterTimeout"],
             " (static 常显=预期终态)" if mode == "static" else ""))
    print("[%s] fcp=%dms lcp=%s(%s)"
          % (mode, d["fcp"],
             d["lcp"][-1]["start"] if d["lcp"] else -1,
             (d["lcp"][-1]["tag"] or d["lcp"][-1]["url"] or "?")
             if d["lcp"] else "?"))
    lts = d["longtasks"]
    if mode == "full":
        print("[%s] longtasks=%d Σdur=%dms(Lighthouse TBT home=%.1fms,"
              "引用归档)" % (mode, len(lts),
                              sum(x["dur"] for x in lts), LH_TBT_HOME_MS))
    else:
        # static 组 Lighthouse 未测:归档摘录只有 full 首页一组,
        # 不把 full 组数字挪用为 static 结论(口径修正 2026-10-13)
        print("[%s] longtasks=%d Σdur=%dms(Lighthouse TBT=未测,"
              "归档摘录仅 full 基准)" % (mode, len(lts),
                                          sum(x["dur"] for x in lts)))
    for x in lts:
        print("[%s]   longtask start=%.0fms dur=%.0fms %s"
              % (mode, x["start"], x["dur"], x["name"]))
    for what in ("menu", "tab", "read"):
        cs = [c for c in d["clicks"] if c["what"] == what and c["paired"]]
        miss = sum(1 for c in d["clicks"]
                   if c["what"] == what and not c.get("paired"))
        skip = sum(1 for x in d.get("dispatch", [])
                   if x.get("what") == what and "skipped" in x)
        print("[%s] %s: inputDelay %s | processing %s | input→paint %s"
              " | missing=%d skipped=%d"
              % (mode, what,
                 dist([c["inputDelay"] for c in cs]),
                 dist([c["processing"] for c in cs]),
                 dist([c["durTotal"] for c in cs]), miss, skip))
        for c in cs:
            if c["overlap"]:
                print("[%s]   OVERLAP %s@%.0fms inputDelay=%.0fms <- %s"
                      % (mode, what, c["start"], c["inputDelay"],
                         c["overlap"]))
    ov_n = sum(1 for c in d["clicks"] if c.get("overlap"))
    ov_delay = [c["inputDelay"] for c in d["clicks"] if c.get("overlap")]
    print("[%s] overlap samples=%d%s"
          % (mode, ov_n,
             (" inputDelay=%s" % ov_delay) if ov_delay else ""))


async def main_async(port):
    httpd = serve_gzip(str(SITE / "dist"), port)
    base = "http://127.0.0.1:%d" % port
    try:
        async with async_playwright() as p:
            launch = ({"executable_path": find_chrome()}
                      if find_chrome() else {})
            b = await p.chromium.launch(**launch)
            print("chromium %s" % b.version)
            for mode in ("full", "static"):
                d = await run_group(b, base, mode)
                pair_clicks(d)
                summarize(mode, d)
                out = LOGS / ("r6-b3-tbt3-compare-%s.json" % mode)
                out.write_text(json.dumps(d, ensure_ascii=False,
                                          indent=1), encoding="utf-8")
                print("[%s] saved %s" % (mode, out))
            await b.close()
    finally:
        httpd.shutdown()
    return 0


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 2 and sys.argv[1] == "--port":
        port = int(sys.argv[2])
    else:
        port = PORT
    return asyncio.run(main_async(port))


if __name__ == "__main__":
    sys.exit(main())
