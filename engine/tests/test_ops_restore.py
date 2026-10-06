"""ops 恢复与 status 测试(种子=scheduling-ops 验收 7/8;§3 规则 8/9)。

真实文件系统+SQLite 文件(非内存库):规则 9 读回校验的"关闭连接后
重开"必须穿透 WAL 与连接缓存,内存库测不出。不变量=活动库完成切换 ⇔
其内 pay_paused=1 已先持久化;任何中断点重启后不存在"活动库已启用而
付费未暂停"。崩溃注入=after_step 回调(进程内等价:崩溃点后不再执行
任何恢复代码,重试即重启)。
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from nanmu_engine.config import load_config
from nanmu_engine.db import connect_db, migrate
from nanmu_engine.ledger import (authorize, reusable_scores,
                                 sync_budget_limits)
from nanmu_engine.ops import (OpsCommandError, pause_issue, restore_backup,
                              status, unpause_issue)
from nanmu_engine.publish import PublishContext, publish_issue

ENGINE_ROOT = Path(__file__).resolve().parents[1]
DIGEST_DIR = "site/src/content/digest"
MARKER_DATE = "2026-09-01"


class Crash(Exception):
    """模拟中断:该步之后恢复序列不再执行(重试=重启后再跑)。"""


@pytest.fixture
def kill_at():
    def _make(step_name):
        def hook(step):
            if step == step_name:
                raise Crash(step)
        return hook
    return _make


def _run(args, cwd, check=True):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args}: {r.stderr or r.stdout}")
    return r.stdout.strip()


def _make_db(path: Path, *, marker=False, seed=None):
    conn = connect_db(str(path))
    migrate(conn)
    if marker:      # 备份独有标记期(证明活动库已被备份替换)
        with conn:
            conn.execute(
                "INSERT INTO digest_issue (issue_date, entry_ids, status,"
                " created_utc, fail_reason) VALUES (?, '[]', 'failed',"
                " '2026-09-01T00:00:00Z', 'E2.upstream')", (MARKER_DATE,))
    if seed:
        seed(conn)
    conn.close()
    return path


def _meta(path: Path, key: str = "pay_paused"):
    """全新连接直读文件(不经任何活动连接缓存)。"""
    import sqlite3
    c = sqlite3.connect(str(path))
    try:
        row = c.execute("SELECT value FROM engine_meta WHERE key=?",
                        (key,)).fetchone()
        return row[0] if row else None
    finally:
        c.close()


def _marker_in(path: Path) -> bool:
    import sqlite3
    c = sqlite3.connect(str(path))
    try:
        return c.execute("SELECT 1 FROM digest_issue WHERE issue_date=?",
                         (MARKER_DATE,)).fetchone() is not None
    finally:
        c.close()


def _assert_invariant(live: Path):
    """不变量:活动库已启用备份内容 ⇒ 其内 pay_paused 已=1(键在且值 1)。

    "除活动库从未被替换"=marker 不在时活动库仍是原库,不约束。
    """
    if _marker_in(live):
        assert _meta(live) == "1", \
            "活动库已切换但付费未暂停(禁绝的中间态)"


def _authorize(conn, config):
    return authorize(conn, config, purpose="score",
                     model="deepseek-flash", request_hash="h" * 64,
                     identity_key="url:https://example.com/a",
                     token_count=1000, issue_date="2026-10-06",
                     origin="initial")


# ---------- 验收 8 主线:恢复置位/闸门/解除 ----------

def test_restore_sets_flag_gate_blocks_and_release_resumes(tmp_path):
    config = load_config(ENGINE_ROOT)
    live = _make_db(tmp_path / "engine.db")
    backup = _make_db(tmp_path / "backup.db", marker=True)

    out = restore_backup(backup, live)
    assert _meta(live) == "1"                    # pay_paused=1 落活动库
    assert _marker_in(live)                      # 备份内容已生效
    assert out["checklist"]                      # 步骤⑤核对清单非空

    conn = connect_db(str(live))
    sync_budget_limits(conn, config)
    r = _authorize(conn, config)                 # 闸门拒绝新增付费
    assert r.status == "rejected" and r.reject_reason == "pay_paused"
    # 只读/复用照常(零新增付费不等于零读取)
    assert conn.execute("SELECT COUNT(*) FROM digest_issue").fetchone()
    assert reusable_scores(conn, [], {"purpose": "score",
                                      "model": "deepseek-flash",
                                      "prompt_version": "pv"}) == {}
    # 人工核对后显式解除 → 恢复授权
    with conn:
        conn.execute(
            "UPDATE engine_meta SET value='0' WHERE key='pay_paused'")
    assert _authorize(conn, config).status == "reserved"
    conn.close()


# ---------- [V2] 文件级强化:关闭重开/切换边界/裸恢复/旧备份 ----------

def test_v2_checkpoint_close_reopen_before_switch(tmp_path, kill_at):
    # ②后中断:副本置位必须已穿透到文件(全新连接读得回),
    # 活动库分毫未动——读回校验不是摆设,WAL 未合并/旧快照都会漏
    live = _make_db(tmp_path / "engine.db")
    backup = _make_db(tmp_path / "backup.db", marker=True)
    pending = Path(str(live) + ".restore-pending")

    with pytest.raises(Crash):
        restore_backup(backup, live, after_step=kill_at("set_flag"))
    assert _meta(live) == "0" and not _marker_in(live)   # 活动库未动
    assert _meta(pending) == "1"                         # 副本已持久化


@pytest.mark.parametrize("step", ["copy", "set_flag", "verify", "switch"])
def test_v2_switch_boundary_crash_states(tmp_path, kill_at, step):
    # ①③后崩溃 → 活动库未动可重试;④后崩溃 → 新活动库已含标志;
    # 任何中断点:不存在"活动库已启用且付费未暂停";重启重试幂等成功
    live = _make_db(tmp_path / "engine.db")
    backup = _make_db(tmp_path / "backup.db", marker=True)

    with pytest.raises(Crash):
        restore_backup(backup, live, after_step=kill_at(step))
    _assert_invariant(live)

    restore_backup(backup, live)                 # 重启后重试
    _assert_invariant(live)
    assert _meta(live) == "1" and _marker_in(live)


def test_v2_bare_restore_key_missing(tmp_path):
    # 绕过命令的裸恢复=键缺失 → 闸门拒绝新增 + status 提示核对
    config = load_config(ENGINE_ROOT)
    live = _make_db(tmp_path / "engine.db")
    conn = connect_db(str(live))
    with conn:
        conn.execute("DELETE FROM engine_meta WHERE key='pay_paused'")
    sync_budget_limits(conn, config)
    r = _authorize(conn, config)
    assert r.status == "rejected" and r.reject_reason == "key_missing"
    assert any("pay_paused" in w for w in status(conn)["warnings"])
    conn.close()


def test_v2_backup_older_than_published_state(tmp_path):
    # 备份时点 draft、实际已 published(远端尖端树内即该内容)→
    # 恢复后经 publish_issue 补记 published(幂等:二次调用零新提交)
    remote = tmp_path / "remote.git"
    _run(["init", "--bare", "-b", "main", str(remote)], tmp_path)
    work = tmp_path / "work"
    _run(["clone", str(remote), str(work)], tmp_path)
    _run(["config", "user.email", "t@t"], work)
    _run(["config", "user.name", "t"], work)

    issue_date = "2026-10-05"
    md = ("---\ndate: '%s'\ngenerated: true\nai_model: m\nentry_count: 1\n"
          "cost_cny: 0.01\ncost_pending: false\n---\n\n## 值得一瞥(压线入选)"
          "\n\n- [t](https://e.com)(s · 展示分 71)——p\n" % issue_date)
    path = work / DIGEST_DIR / f"{issue_date}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")
    _run(["add", "."], work)
    _run(["commit", "-m", "digest", "-q"], work)
    _run(["push", "origin", "main"], work)       # 线上已是该内容(实际 published)
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()

    def seed_draft(conn):                        # 备份时点:该期=draft
        cur = conn.execute(
            "INSERT INTO entry (identity_key, url, title, source_name,"
            " source_tier, discovered_utc, content_text, status, claim_issue)"
            " VALUES ('k1', 'https://e.com', 't', 's', 'T1',"
            " '2026-10-05T00:00:00Z', 'b', 'selected', ?)", (issue_date,))
        with conn:
            conn.execute(
                "INSERT INTO digest_issue (issue_date, entry_ids,"
                " markdown_path, content_sha256, cost_cny, status,"
                " created_utc) VALUES (?,?,?,?,?,'draft','2026-10-05T00:00:00Z')",
                (issue_date, json.dumps([cur.lastrowid]), str(path), sha, 0.01))

    live = _make_db(tmp_path / "engine.db", seed=seed_draft)
    backup = _make_db(tmp_path / "backup.db", seed=seed_draft)
    restore_backup(backup, live)                 # 恢复旧快照:期回到 draft

    conn = connect_db(str(live))
    ctx = PublishContext(
        workdir=work, remote_url=str(remote), branch="main",
        digest_dir=DIGEST_DIR, site_base="https://blog.example",
        fetch_release_sha=lambda: _run(["rev-parse", "origin/main"], work),
        fetch_url_ok=lambda url: True)
    assert publish_issue(conn, issue_date, ctx,
                         final_keys=["k1"]).status == "published"   # 补记
    head = _run(["rev-parse", "origin/main"], work)
    assert publish_issue(conn, issue_date, ctx,
                         final_keys=["k1"]).status == "published"   # 幂等
    assert _run(["rev-parse", "origin/main"], work) == head        # 零新提交
    conn.close()


# ---------- 验收 7:status 五组事实(规则 8;§3.5 样例字段) ----------

def _seed_rich_issue(conn):
    """一期混合现场:freeze(paused)+failed 行+三类条目+结算/未决 attempt。"""
    ids = []
    for key, st in (("k-scored", "scored"), ("k-selected", "selected"),
                    ("k-used", "used")):
        cur = conn.execute(
            "INSERT INTO entry (identity_key, url, title, source_name,"
            " source_tier, discovered_utc, content_text, status)"
            " VALUES (?, 'https://e.com', 't', 's', 'T1',"
            " '2026-10-06T00:00:00Z', 'b', ?)", (key, st))
        ids.append(cur.lastrowid)
    manifest = json.dumps([{"entry_id": i, "identity_key": f"k{i}"}
                           for i in ids])
    with conn:
        conn.execute(
            "INSERT INTO issue_freeze (issue_date, frozen_utc, entry_count,"
            " manifest_json, paused, paused_reason, paused_utc)"
            " VALUES ('2026-10-06', '2026-10-06T00:30:00Z', 3, ?, 1,"
            " '排查', '2026-10-06T01:00:00Z')", (manifest,))
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, status,"
            " created_utc, fail_reason, last_exit, last_run_utc)"
            " VALUES ('2026-10-06', '[]', 'failed', '2026-10-06T00:00:00Z',"
            " 'E6.all_failed', 3, '2026-10-06T00:41:05Z')")
        for i, (rstatus, astatus, reserved, actual) in enumerate(
                [("completed", "received", 1000, 1000),
                 ("completed", "received", 2000, 2500),
                 ("unknown", "unknown", 500, None)]):
            cur = conn.execute(
                "INSERT INTO receipt (logical_key, provider, endpoint,"
                " request_hash, service, purpose, model, status, created_utc)"
                " VALUES (?, 'deepseek', '/chat/completions', 'rh', 'llm',"
                " 'score', 'deepseek-flash', ?, '2026-10-06T00:00:00Z')",
                (f"lk-{i}", rstatus))
            conn.execute(
                "INSERT INTO receipt_attempt (receipt_id, attempt_no,"
                " issue_date, started_utc, status, attempt_origin,"
                " reserved_micro_cny, actual_micro_cny, pricing_version)"
                " VALUES (?, 1, '2026-10-06', '2026-10-06T00:00:00Z', ?,"
                " 'initial', ?, ?, 'v')",
                (cur.lastrowid, astatus, reserved, actual))


def test_status_issue_reports_five_fact_groups(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    _seed_rich_issue(conn)

    st = status(conn, "2026-10-06")
    assert st["status"] == "failed"                       # ①期状态
    assert st["paused"] is True and st["paused_reason"] == "排查"
    assert st["fail_reason"] == "E6.all_failed"
    assert st["entries"] == {"frozen": 3, "scored": 1,    # ②条目计数
                             "selected": 1, "used": 1}
    assert st["attempts"]["settled_count"] == 2           # ③结算与未决
    assert st["attempts"]["settled_cny"] == pytest.approx(0.0035)
    assert st["attempts"]["unsettled_count"] == 1
    assert st["attempts"]["reserved_cny"] == pytest.approx(0.0005)
    assert st["last_run"] == {"exit": 3,                  # ④最近 run
                              "utc": "2026-10-06T00:41:05Z"}
    assert "重跑" in st["next"]                           # ⑤下一步建议
    conn.close()


def test_status_generating_without_digest_row(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    with conn:
        conn.execute(
            "INSERT INTO issue_freeze (issue_date, frozen_utc, entry_count,"
            " manifest_json) VALUES ('2026-10-06', '2026-10-06T00:30:00Z',"
            " 0, '[]')")
    st = status(conn, "2026-10-06")
    assert st["status"] == "generating"           # ①freeze 在无行=生成中
    assert st["paused"] is False
    assert st["entries"]["frozen"] == 0
    assert "调度" in st["next"] or "续跑" in st["next"]
    conn.close()


def test_status_withdrawn_published_stays_published(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, markdown_path,"
            " content_sha256, status, created_utc, withdrawn_utc,"
            " withdraw_commit)"
            " VALUES ('2026-10-06', '[]', 'p', 'x', 'published',"
            " '2026-10-06T00:00:00Z', '2026-10-06T02:00:00Z', 'sha1')")
    st = status(conn, "2026-10-06")
    assert st["status"] == "published" and st["withdrawn"] is True
    assert st["withdraw_commit"] == "sha1"
    conn.close()


def test_status_no_issue_lists_open_and_today(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    _seed_rich_issue(conn)                        # 2026-10-06 failed(不进 open)
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, markdown_path,"
            " content_sha256, status, created_utc)"
            " VALUES ('2026-10-05', '[]', 'p', 'x', 'draft',"
            " '2026-10-05T00:00:00Z')")
        conn.execute(
            "INSERT INTO issue_freeze (issue_date, frozen_utc, entry_count,"
            " manifest_json) VALUES ('2026-10-04', '2026-10-04T00:30:00Z',"
            " 0, '[]')")                          # 生成中(无行)
    st = status(conn, today="2026-10-06")
    assert [o["issue_date"] for o in st["open"]] == ["2026-10-04",
                                                     "2026-10-05"]  # 升序
    assert all(o["status"] in ("generating", "draft", "submitted")
               for o in st["open"])
    assert st["today"]["issue_date"] == "2026-10-06"
    assert st["today"]["status"] == "failed"
    conn.close()


# ---------- 规则 4:pause/unpause ----------

def test_pause_unpause_issue(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    with conn:
        conn.execute(
            "INSERT INTO issue_freeze (issue_date, frozen_utc, entry_count,"
            " manifest_json) VALUES ('2026-10-06', '2026-10-06T00:30:00Z',"
            " 0, '[]')")
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, markdown_path,"
            " content_sha256, status, created_utc)"
            " VALUES ('2026-10-06', '[]', 'p', 'x', 'draft',"
            " '2026-10-06T00:00:00Z')")

    pause_issue(conn, "2026-10-06", reason="撤回防护")
    row = conn.execute("SELECT paused, paused_reason FROM issue_freeze"
                       " WHERE issue_date='2026-10-06'").fetchone()
    assert row == (1, "撤回防护")

    unpause_issue(conn, "2026-10-06")             # 只恢复调度可见性
    assert conn.execute("SELECT paused FROM issue_freeze WHERE"
                        " issue_date='2026-10-06'").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-06'").fetchone()[0] == "draft"

    with pytest.raises(OpsCommandError):          # 参数错→拒绝并列可用期
        pause_issue(conn, "1999-01-01", reason="x")
    conn.close()
