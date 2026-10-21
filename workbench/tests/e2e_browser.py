# -*- coding: utf-8 -*-
"""工作台批 1 浏览器 e2e 验收(2026-10-21)。

对象:workbench 本地服务(node src/server.js,127.0.0.1 独立端口,独立临时
数据目录,占位口令非真实凭据)。覆盖批 1 验收的浏览器侧条目:

- A 登录→新建→输入→保存→返回列表→重开,内容与元数据一致(验收①)
- B 关闭页面+重启服务后已保存草稿完整恢复;重启即失效会话回登录(验收②⑤)
- C 两窗口同 rev 保存:先者成功,后者明确冲突并展示本窗口内容,不静默覆盖(验收③)
- D 保存失败(服务停)不显示「已保存」;输入经浏览器补救位恢复(验收④)
- E 持续输入 60s 周期保存落盘(防抖被压制时兜底);保存飞行期间的新输入
  不被旧响应误标为已保存(验收⑥)
- F 登出后访问受保护页回登录页(验收⑦浏览器侧;API 拒绝/限速/CSRF 由接口测试覆盖)
- G 服务日志不含口令与草稿正文(验收⑨)

边界:本地隔离;不连生产、不推送、不改公开站产品代码。
用法(在 site/ 目录,复用其 Playwright 环境):
python -I ../workbench/tests/e2e_browser.py
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")  # Windows 管道下默认 GBK 会乱码

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "site" / "scripts"))
from verify_browser import find_chrome  # noqa: E402 跨目录复用(-I 不自动加)

PORT = 8791
PASSWORD = "e2e-placeholder"                       # 占位口令,非真实凭据
BASE = f"http://127.0.0.1:{PORT}"
SENTINEL = "E2E-SENTINEL-正文标记"
SENTINEL_FAIL = "E2E-FAIL-未保存正文"

RESULTS = []


def check(label, ok, detail=""):
    RESULTS.append(ok)
    mark = "PASS" if ok else "FAIL"
    print(f"{mark} {label}" + (f"  [{detail}]" if detail else ""), flush=True)
    return ok


def status_text(page):
    return page.text_content("#status") or ""


def wait_loaded(page):
    page.wait_for_function(
        "() => { const s = document.getElementById('status');"
        " return s && !s.textContent.includes('加载中'); }", timeout=15000)


def port_free(port):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return False  # 有人监听(可能是上次残留进程)
    except OSError:
        return True


def start_server(drafts_dir, log_path):
    if not port_free(PORT):
        raise RuntimeError(f"端口 {PORT} 已被占用(残留进程?),e2e 拒绝连到不明服务")
    env = {
        **os.environ,
        "PORT": str(PORT),
        "WB_DEV_PASSWORD": PASSWORD,
        "WB_DRAFTS_DIR": str(drafts_dir),
    }
    log = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        ["node", "src/server.js"], cwd=str(REPO / "workbench"),
        env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    for _ in range(120):
        try:
            with urllib.request.urlopen(f"{BASE}/login", timeout=1) as resp:
                if resp.status == 200:
                    return proc, log
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("工作台服务未就绪(120 次探测失败)")


def login(page):
    page.goto(f"{BASE}/login")
    page.fill("#password", PASSWORD)
    page.click("#login-btn")
    page.wait_for_url(f"{BASE}/", timeout=15000)


def save_and_wait(page, rev_expect, timeout=15000):
    page.keyboard.press("Control+s")
    page.wait_for_function(
        f"() => document.getElementById('status').textContent.includes('rev {rev_expect}')"
        " && document.getElementById('status').textContent.includes('已保存')",
        timeout=timeout)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="wb-e2e-"))
    drafts_dir = tmp / "drafts"
    drafts_dir.mkdir()
    srv_log = tmp / "server.log"
    proc, logf = start_server(drafts_dir, srv_log)
    browser = None
    pw_ctx = None
    try:
        with sync_playwright() as pw:
            launch = {"executable_path": find_chrome()} if find_chrome() else {}
            browser = pw.chromium.launch(**launch)
            pw_ctx = browser.new_context()
            page = pw_ctx.new_page()

            # ---- A 登录→新建→保存→列表→重开 ----
            page.goto(f"{BASE}/")
            page.wait_for_url("**/login")
            check("A1 未登录访问 / 重定向登录页", page.url.endswith("/login"))
            login(page)
            check("A2 正确口令登录进入列表页", page.url == f"{BASE}/")

            page.click("a:has-text('新建草稿')")
            page.wait_for_url("**/edit/new")
            page.fill("#f-slug", "e2e-first-draft")
            page.fill("#f-title", "批一验收样稿")
            page.fill("#f-date", "2026-10-21")
            page.fill("#f-tags", "验收, 工作台")
            page.fill("#f-body", f"第一版正文 {SENTINEL}")
            save_and_wait(page, 1)
            check("A3 新建草稿保存成功,状态显示「已保存 …(rev 1)」", True)

            page.fill("#f-body", f"第二版正文 {SENTINEL}")
            save_and_wait(page, 2)
            check("A4 修改后保存 rev 2", True)

            page.click("a:has-text('返回列表')")
            page.wait_for_url(f"{BASE}/")
            page.wait_for_selector("text=e2e-first-draft")
            check("A5 列表出现该草稿行", True)

            page.click("tr:has-text('e2e-first-draft') a:has-text('编辑')")
            page.wait_for_url("**/edit/e2e-first-draft")
            wait_loaded(page)
            same = (
                page.input_value("#f-body") == f"第二版正文 {SENTINEL}"
                and page.input_value("#f-title") == "批一验收样稿"
                and page.input_value("#f-date") == "2026-10-21"
                and page.input_value("#f-tags") == "验收, 工作台"
                and page.input_value("#f-slug") == "e2e-first-draft"
            )
            check("A6 重开后正文与元数据一致", same)
            check("A7 重开后 slug 只读", page.get_attribute("#f-slug", "readonly") is not None)

            # ---- B 重启服务恢复 ----
            proc.terminate()
            proc.wait(timeout=10)
            logf.close()
            proc, logf = start_server(drafts_dir, srv_log)
            page.reload()
            page.wait_for_url("**/login", timeout=15000)
            check("B1 服务重启后会话(内存表)失效,页面回登录", True)
            login(page)
            page.goto(f"{BASE}/edit/e2e-first-draft")
            wait_loaded(page)
            ok = (
                page.input_value("#f-body") == f"第二版正文 {SENTINEL}"
                and page.input_value("#f-title") == "批一验收样稿"
                and page.input_value("#f-date") == "2026-10-21"
            )
            check("B2 重启后已保存草稿完整恢复(正文+元数据+rev 同源)", ok)

            # ---- C 双窗口同 rev 冲突 ----
            p1 = pw_ctx.new_page()
            p1.goto(f"{BASE}/edit/e2e-first-draft")
            wait_loaded(p1)
            p2 = pw_ctx.new_page()
            p2.goto(f"{BASE}/edit/e2e-first-draft")
            wait_loaded(p2)
            p1.fill("#f-body", "窗口甲修改的版本")
            p2.fill("#f-body", "窗口乙修改的版本")
            save_and_wait(p1, 3)
            check("C1 先保存窗口成功(rev 3)", True)
            p2.keyboard.press("Control+s")
            p2.wait_for_selector("#conflict-box:not([hidden])", timeout=15000)
            check("C2 后保存窗口收到明确版本冲突提示(非静默覆盖)", True)
            local_shown = p2.input_value("#conflict-local")
            check("C3 冲突提示展示本窗口未保存内容供取舍", "窗口乙修改的版本" in local_shown)
            p2.on("dialog", lambda d: d.accept())
            p2.click("#conflict-refresh")
            wait_loaded(p2)
            check("C4 冲突后刷新加载另一窗口已保存版本",
                  p2.input_value("#f-body") == "窗口甲修改的版本")
            p1.close()
            p2.close()

            # ---- D 保存失败与浏览器补救位 ----
            p3 = pw_ctx.new_page()
            p3.goto(f"{BASE}/edit/e2e-first-draft")
            wait_loaded(p3)
            p3.fill("#f-body", f"失败场景正文 {SENTINEL_FAIL}")
            time.sleep(2.6)  # localStorage 节流 2s 落补救位
            proc.terminate()
            proc.wait(timeout=10)
            logf.close()
            p3.keyboard.press("Control+s")
            p3.wait_for_function(
                "() => document.getElementById('status').textContent.includes('保存失败')",
                timeout=20000)
            st = status_text(p3)
            check("D1 保存失败时状态条如实转「保存失败」,不显示「已保存」",
                  "保存失败" in st and "已保存" not in st)
            proc, logf = start_server(drafts_dir, srv_log)
            p3.on("dialog", lambda d: d.accept())  # 接受恢复提示/离开确认
            # 重启后服务端会话已失效:先回登录,再打开草稿;
            # 浏览器 localStorage 的补救位仍在,打开时应提示恢复
            p3.goto(f"{BASE}/edit/e2e-first-draft")
            if p3.url.endswith("/login"):
                login(p3)
                p3.goto(f"{BASE}/edit/e2e-first-draft")
            page_ok = p3.wait_for_function(
                "() => document.getElementById('f-body')"
                ".value.includes('%s')" % SENTINEL_FAIL, timeout=15000)
            check("D2 服务恢复后重开,提示并恢复浏览器本地未保存内容", bool(page_ok))
            check("D3 恢复后状态如实显示未保存", "未保存" in status_text(p3))
            p3.close()

            # ---- E 周期保存上限 + 旧响应不误标 ----
            # 持续输入(约 1.3s/轮):防抖若生效应在 30s(约 23 轮)保存;
            # 防抖被正确压制时应到 60s 周期(约 46 轮)才落盘
            p4 = pw_ctx.new_page()
            p4.goto(f"{BASE}/edit/e2e-first-draft")
            wait_loaded(p4)
            p4.fill("#f-body", "周期保存验证起点")
            save_round = None
            dirty_at_32 = False
            for i in range(1, 80):
                p4.type("#f-body", "字")
                time.sleep(1.0)
                st = p4.get_attribute("#status", "data-state")
                if i == 32 and st == "dirty":
                    dirty_at_32 = True  # 42s+ 仍在输入且未发生防抖保存
                if st == "clean":
                    save_round = i
                    break
            check("E1 持续输入压制 30s 停顿防抖(第 32 轮仍 dirty)", dirty_at_32)
            check(f"E2 周期保存兜底落盘(第 {save_round} 轮自动保存,不早于 40 轮)",
                  save_round is not None and save_round >= 40)

            p5 = pw_ctx.new_page()
            p5.goto(f"{BASE}/edit/e2e-first-draft")
            wait_loaded(p5)
            p5.route("**/api/drafts/*", lambda route: (
                time.sleep(2.5), route.continue_()))

            def unroute():
                p5.unroute("**/api/drafts/*")
            p5.fill("#f-body", "旧响应验证正文")
            p5.keyboard.press("Control+s")
            time.sleep(0.8)  # 请求仍在飞行
            p5.fill("#f-body", "飞行期间的新输入")
            p5.wait_for_function(
                "() => { const el = document.getElementById('status');"
                " return el.dataset.state === 'dirty'"
                " && el.textContent.includes('已保存至 rev'); }", timeout=15000)
            check("E3 保存成功返回不把之后新输入误标为已保存(状态=未保存(已保存至 rev N))", True)
            unroute()
            p4.close()
            p5.close()

            # ---- F 登出 ----
            page.goto(f"{BASE}/")
            page.wait_for_selector("#logout-btn")
            page.click("#logout-btn")
            page.wait_for_url("**/login", timeout=15000)
            page.goto(f"{BASE}/")
            page.wait_for_url("**/login")
            check("F1 登出后受保护页面回登录页", page.url.endswith("/login"))

            browser.close()
            browser = None

        # ---- G 日志脱敏 ----
        log_text = srv_log.read_text(encoding="utf-8", errors="replace")
        check("G1 服务日志不含口令", PASSWORD not in log_text)
        check("G2 服务日志不含草稿正文标记",
              SENTINEL not in log_text and SENTINEL_FAIL not in log_text
              and "窗口甲修改的版本" not in log_text)

    finally:
        # 逐项兜底:任何一步失败不得阻止后续清理(此前 browser.close() 先抛
        # 错曾跳过 terminate,残留进程占端口导致下次 e2e 连到旧服务)
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            pass
        try:
            logf.close()
        except Exception:
            pass

    total, passed = len(RESULTS), sum(RESULTS)
    print(f"\n== e2e 结果:{passed}/{total} PASS ==")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
