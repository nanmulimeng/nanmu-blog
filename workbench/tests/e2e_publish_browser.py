# -*- coding: utf-8 -*-
"""批 4 前端发布/撤下浏览器 e2e(2026-10-25)。

对象:server.js 真进程+临时裸双远端(不碰生产)+浏览器走真实 UI:
登录→新建草稿→保存→点「发布」(确认弹窗)→编辑器状态「已上线」
→列表页操作区「已上线」→「撤下」(影响面确认)→「已撤下」。
用法(workbench/ 下):python -I tests/e2e_publish_browser.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
WB = Path(__file__).resolve().parents[1]
PW = "e2e-placeholder-password"
GE = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
      "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
ok = []


def check(name, cond, detail=""):
    ok.append(cond)
    print(("PASS" if cond else "FAIL"), name, detail)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="wbpub-"))

    def git(a, cwd):
        return subprocess.check_output(["git"] + a, cwd=cwd,
                                       env={**os.environ, **GE}, timeout=30)

    git(["init", "--bare", "-b", "main", str(tmp / "deploy.git")], str(tmp))
    seed = tmp / "seed"
    git(["clone", str(tmp / "deploy.git"), str(seed)], str(tmp))
    (seed / "site" / "src" / "content" / "posts").mkdir(parents=True)
    (seed / "site" / "README").write_text("x", encoding="utf-8")
    git(["add", "-A"], str(seed)); git(["commit", "-m", "s"], str(seed))
    git(["push", "origin", "HEAD:main"], str(seed))
    git(["init", "--bare", "-b", "main", str(tmp / "github.git")], str(tmp))
    git(["push", str(tmp / "github.git"), "main:main"], str(tmp / "deploy.git"))

    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    base = f"http://127.0.0.1:{port}"
    srv = subprocess.Popen(
        ["node", "src/server.js"], cwd=str(WB),
        env={**os.environ, "PORT": str(port), "WB_DEV_PASSWORD": PW,
             "WB_DRAFTS_DIR": str(tmp / "drafts"), "WB_PREVIEWS_DIR": str(tmp / "previews"),
             "WB_GIT_REPO": str(tmp / "repo.git"), "WB_GIT_WT": str(tmp / "repo.wt"),
             "WB_OPS_DIR": str(tmp / "ops"),
             "WB_REMOTE_GITHUB": str(tmp / "github.git"),
             "WB_REMOTE_DEPLOY": str(tmp / "deploy.git")},
        stdout=open(tmp / "srv.log", "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(base + "/login", timeout=1); break
            except Exception:
                time.sleep(0.3)
        with sync_playwright() as pw:
            cand = Path.home() / "AppData/Local/ms-playwright"
            exe = {}
            if cand.is_dir():
                hits = [p for p in cand.glob("chromium-*/chrome-win64/chrome.exe")]
                if hits:
                    exe = {"executable_path": str(max(hits))}
            b = pw.chromium.launch(**exe)
            pg = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
            dialogs = []
            pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
            perrs = []
            bad_resp = []
            pg.on("response", lambda r: bad_resp.append((r.status, r.url)) if r.status >= 400 else None)
            pg.on("pageerror", lambda e: perrs.append(str(e)))
            pg.on("console", lambda m: perrs.append(m.type + ": " + m.text) if m.type == "error" else None)

            pg.goto(base + "/login")
            pg.fill("input[type=password]", PW)
            pg.click("button[type=submit]")
            pg.wait_for_url("**/", timeout=8000)

            # 新建→保存
            pg.goto(base + "/edit/launch-day")
            pg.fill("#f-slug", "launch-day")
            pg.fill("#f-title", "上线日")
            pg.fill("#f-date", "2026-10-25")
            pg.fill("#f-body", "---\ntitle: 上线日\npubDate: 2026-10-25\ntags: []\n---\n\n正文。\n")
            pg.click("#save-btn")
            pg.wait_for_selector("#status[data-state=clean]", timeout=8000)
            check("H1 保存成功(clean)", True)

            # 发布(UI 弹窗确认)
            pg.click("#publish-btn")
            pg.wait_for_timeout(800)
            print("  [probe] after click status:", pg.inner_text("#status"),
                  "| state:", pg.evaluate("() => document.getElementById('status').dataset.state"))
            try:
                pg.wait_for_function(
                    "() => document.getElementById('status').textContent.includes('已上线')",
                    timeout=90000)
            except Exception:
                print("  [diag] status:", pg.inner_text("#status"))
                print("  [diag] pageerrors:", perrs[:6])
                print("  [diag] dialogs:", dialogs)
                ops_dir = tmp / "ops"
                if ops_dir.is_dir():
                    for f in ops_dir.glob("*.json"):
                        print("  [diag] op:", f.read_text(encoding="utf-8")[:400])
                print("  [diag] 4xx/5xx:", bad_resp[:8])
                print("  [diag] srv.log tail:",
                      (tmp / "srv.log").read_text(encoding="utf-8", errors="replace")[-1500:])
                raise
            check("H2 编辑器显示已上线", True, pg.inner_text("#status")[:40])
            d_sha = git(["rev-parse", "main"], str(tmp / "deploy.git")).decode().strip()
            g_sha = git(["rev-parse", "main"], str(tmp / "github.git")).decode().strip()
            check("H3 双远端已接收", d_sha == g_sha and d_sha[:7] != "", d_sha[:7])
            check("H4 发布确认弹窗出现过(二次确认)",
                  any("发布" in m for m in dialogs), dialogs[:1])

            # 列表页:操作区已上线→撤下(影响面弹窗)
            pg.goto(base + "/")
            pg.wait_for_selector("table #ops-tbody button[data-withdraw]", timeout=10000)
            row = pg.inner_text("#ops-tbody")
            check("H5 列表操作区显示已上线", "已上线" in row and "launch-day" in row)
            pg.click("button[data-withdraw=launch-day]")
            pg.wait_for_selector("#ops-tbody >> text=已撤下", timeout=90000)
            check("H6 撤下完成显示已撤下", True)
            check("H7 撤下弹窗含影响面说明",
                  any("404" in m for m in dialogs), [m[:30] for m in dialogs if "404" in m][:1])
            d_sha2 = git(["rev-parse", "main"], str(tmp / "deploy.git")).decode().strip()
            check("H8 撤下已推双远端", d_sha2 != d_sha, d_sha2[:7])

            srv_log = (tmp / "srv.log").read_text(encoding="utf-8", errors="replace")
            check("H9 服务日志不含口令", PW not in srv_log)
            b.close()
        srv.terminate(); srv.wait(timeout=5)
        print(f"\n== 发布/撤下浏览器 e2e: {sum(ok)}/{len(ok)} ==")
        sys.exit(0 if all(ok) else 1)
    finally:
        try:
            srv.terminate(); srv.wait(timeout=5)
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
