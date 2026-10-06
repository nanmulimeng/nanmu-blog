"""调度运行序测试(scheduling-ops §3 规则 1-2;种子=验收 1/1b/2/3/4/5)。
运行序=先恢复存量(issue_date 升序、期内先只读、paused 跳过、恢复预算
recover_budget_s)→当天新期→收尾 last_exit/last_run_utc;截止锚点=
issue_freeze.frozen_utc 唯一。LLM 一律 httpx.MockTransport 替身,远端=
本地 bare repo 夹具,零真实网络。"""

import dataclasses
import hashlib
import itertools
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from nanmu_engine.config import (ExcludeEntry, SourceEntry, SourcesConfig,
                                 load_config)
from nanmu_engine.db import connect_db, migrate
from nanmu_engine.ledger import (sync_budget_limits,
                                 write_calibration_record)
from nanmu_engine.publish import PublishContext
from nanmu_engine.run import abandon_issue, rerun_issue, run_once

from test_collect import _add_item, _add_source, _make_upstream
from test_publish import DIGEST_DIR, _run

ENGINE_ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 6, 8, 35, tzinfo=timezone.utc)

_USAGE = {"prompt_tokens": 50, "completion_tokens": 20,
          "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 50}


@pytest.fixture
def env(tmp_path):
    remote = tmp_path / "remote.git"
    _run(["init", "--bare", "-b", "main", str(remote)], tmp_path)
    work = tmp_path / "work"
    _run(["clone", str(remote), str(work)], tmp_path)
    _run(["config", "user.email", "t@t"], work)
    _run(["config", "user.name", "t"], work)
    (work / "README.md").write_text("site", encoding="utf-8")
    _run(["add", "."], work)
    _run(["commit", "-m", "init", "-q"], work)
    _run(["push", "origin", "main"], work)

    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    config = load_config(ENGINE_ROOT)
    sync_budget_limits(conn, config)
    write_calibration_record(conn, config, coefficient=1.0,
                            results=[], passed=True)
    config = dataclasses.replace(
        config, sources=SourcesConfig(
            1, "T2", (SourceEntry(name="src-a", tier="T1", priority=10),), ()))

    up_conn, upstream_path = _make_upstream(tmp_path)
    sid = _add_source(up_conn, "src-a")

    state = {"url_ok": True}
    ctx = PublishContext(
        workdir=work, remote_url=str(remote), branch="main",
        digest_dir=DIGEST_DIR, site_base="https://blog.example",
        fetch_release_sha=lambda: _run(["rev-parse", "origin/main"], work)
        or None,
        fetch_url_ok=lambda url: state["url_ok"])

    sent = []

    def sender(dedup_key, message):
        sent.append((dedup_key, message))
        return "sent"

    return {"conn": conn, "config": config, "ctx": ctx, "work": work,
            "state": state, "up_conn": up_conn, "up_sid": sid,
            "upstream_path": upstream_path, "sent": sent,
            "sender": sender, "tmp_path": tmp_path}


def _transport(config, *, score=80, score_fail_marker=None,
               score_fail_status=500):
    """替身:understand 按 system prompt 区分;评分按序返回 score;
    user 内容含 score_fail_marker 的评分请求返回指定 HTTP 状态
    (500=E3.http 可重试;400=E1.request no_retry)。"""
    understand_head = config.prompts.understand.text[:40]
    seq = itertools.count(1)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        system = body["messages"][0]["content"]
        user = body["messages"][1]["content"]
        n = next(seq)
        if system.startswith(understand_head):
            return httpx.Response(200, json={
                "id": f"r{n}", "choices": [{"finish_reason": "stop",
                 "message": {"content": json.dumps({
                     "title_zh": "中文标题", "summary": "一句话摘要。",
                     "reason": "推荐理由。", "tags": ["标签"]}, ensure_ascii=False)}}],
                "usage": _USAGE})
        if score_fail_marker and score_fail_marker in user:
            return httpx.Response(score_fail_status, json={"error": "boom"})
        return httpx.Response(200, json={
            "id": f"r{n}", "choices": [{"finish_reason": "stop",
             "message": {"content": json.dumps({"attentionScore": score})}}],
            "usage": _USAGE})
    return httpx.MockTransport(handler)


def _entry(conn, key, title="标题A", body="正文内容若干。", *, status="pending",
           claim=None, url=None):
    url = url or f"https://e.com/{key}"
    cur = conn.execute(
        "INSERT INTO entry (identity_key, url, title, source_name,"
        " source_tier, discovered_utc, content_text, status, claim_issue)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (key, url, title, "src-a", "T1",
         "2026-10-05T00:00:00Z", body, status, claim))
    conn.commit()
    return {"identity_key": key, "entry_id": cur.lastrowid,
            "url": url, "title": title,
            "source_name": "src-a", "source_tier": "T1",
            "published_utc": None, "discovered_utc": "2026-10-05T00:00:00Z",
            "content_text": body,
            "content_hash": hashlib.sha256(body.encode()).hexdigest()}


def _freeze(conn, issue_date, members, *, frozen, paused=0, reason=None):
    with conn:
        conn.execute(
            "INSERT INTO issue_freeze (issue_date, frozen_utc, entry_count,"
            " manifest_json, paused, paused_reason, paused_utc)"
            " VALUES (?,?,?,?,?,?,?)",
            (issue_date, frozen, len(members),
             json.dumps(members, ensure_ascii=False), paused, reason,
             frozen if paused else None))


def _digest_file(work, issue_date, entry_count=1):
    md = ("---\ndate: '%s'\ngenerated: true\nai_model: m\n"
          "entry_count: %d\ncost_cny: 0.01\ncost_pending: false\n---\n"
          "\n## 值得一瞥(压线入选)\n\n- [t](https://e.com)(s · 展示分 71)"
          "——p\n" % (issue_date, entry_count))
    path = work / DIGEST_DIR / f"{issue_date}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(md, encoding="utf-8")
    return path, hashlib.sha256(md.encode("utf-8")).hexdigest()


def _draft_row(conn, work, issue_date, entry_ids, *, status="draft",
               push=False, frozen=None):
    """落一份产物文件+提交(可选 push)+digest_issue 行。"""
    path, sha = _digest_file(work, issue_date, len(entry_ids))
    _run(["add", "."], work)
    _run(["commit", "-m", f"digest {issue_date}", "-q"], work)
    if push:
        _run(["push", "origin", "main"], work)
    commit = _run(["rev-parse", "HEAD"], work)
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, markdown_path,"
            " content_sha256, git_commit, cost_cny, status, created_utc,"
            " updated_utc) VALUES (?,?,?,?,?,?,?, '2026-10-03T00:00:00Z',"
            " '2026-10-03T00:00:00Z')",
            (issue_date, json.dumps(list(entry_ids)), str(path), sha, commit,
             0.01, status))
    if frozen:                                   # draft/submitted 期配冻结行
        with conn:
            conn.execute(
                "INSERT INTO issue_freeze (issue_date, frozen_utc,"
                " entry_count, manifest_json) VALUES (?,?,0,'[]')",
                (issue_date, frozen))
    return sha, commit


def _statuses(conn):
    return dict(conn.execute(
        "SELECT issue_date, status FROM digest_issue ORDER BY issue_date"
    ).fetchall())


def _attempts_for(conn, issue_date):
    return conn.execute(
        "SELECT COUNT(*) FROM receipt_attempt WHERE issue_date=?",
        (issue_date,)).fetchone()[0]


def _run_once(env, *, today="2026-10-06", now=NOW, transport=None,
              upstream=None, events=None, **kw):
    return run_once(
        env["conn"], env["config"], upstream_path=upstream or env["upstream_path"],
        publish_ctx=env["ctx"], transport=transport, now=now, today=today,
        notify_send=env["sender"], events=events, **kw)


# ---------- 验收 1:运行序(升序恢复、期内先只读、paused 跳过、后新期) ----------

def test_run_order_recovers_oldest_first_then_new_issue(env):
    conn = env["conn"]
    # 10-02:paused 生成中(零动作)
    p1 = _entry(conn, "k-paused", status="pending")
    _freeze(conn, "2026-10-02", [p1], frozen="2026-10-02T08:31:00Z",
            paused=1, reason="人工暂停")
    # 10-03:submitted(只读线上确认→published)
    c1 = _entry(conn, "k-sub", status="selected", claim="2026-10-03")
    _draft_row(conn, env["work"], "2026-10-03", [c1["entry_id"]],
               status="submitted", push=True, frozen="2026-10-03T08:31:00Z")
    # 10-04:draft 未 push(发布恢复→push→published;frozen=10-05 属 D+1 窗)
    c2 = _entry(conn, "k-draft", status="selected", claim="2026-10-04")
    _draft_row(conn, env["work"], "2026-10-04", [c2["entry_id"]],
               status="draft", frozen="2026-10-05T08:31:00Z")
    # 10-05:生成中(续跑:评分→摘要→组装→发布)
    c3 = _entry(conn, "k-gen")
    _freeze(conn, "2026-10-05", [c3], frozen="2026-10-05T08:31:00Z")
    # 上游放 1 条→当天新期候选
    _add_item(env["up_conn"], env["up_sid"], "https://e.com/new1", "新条目",
              fetched=datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc),
              content="新正文。")

    events = []
    code = _run_once(env, transport=_transport(env["config"]),
                     events=events.append)

    assert code == 0
    phases = [e for e in events if e.startswith("phase:")]
    assert phases == [
        "phase:skip_paused:2026-10-02", "phase:recover:2026-10-03",
        "phase:recover:2026-10-04", "phase:recover:2026-10-05",
        "phase:new:2026-10-06"]
    st = _statuses(conn)
    assert st == {"2026-10-03": "published", "2026-10-04": "published",
                  "2026-10-05": "published", "2026-10-06": "published"}
    # paused 期零动作;生成中/新期成员经终态清算 used
    assert conn.execute("SELECT status, claim_issue FROM entry WHERE"
                        " identity_key='k-paused'").fetchone() == \
        ("pending", None)
    for key in ("k-sub", "k-draft", "k-gen"):
        assert conn.execute("SELECT status FROM entry WHERE identity_key=?",
                            (key,)).fetchone()[0] == "used"
    assert _attempts_for(conn, "2026-10-02") == 0


# ---------- 验收 1b:恢复预算耗尽不挤占新期(旧期保存状态继续新期) ----------

def test_recovery_budget_exhausted_spares_new_issue(env):
    conn = env["conn"]
    x1 = _entry(conn, "k-oldfail", title="OLDFAIL 旧期A")
    _freeze(conn, "2026-10-04", [x1], frozen="2026-10-05T08:31:00Z")
    x2 = _entry(conn, "k-spare")
    _freeze(conn, "2026-10-05", [x2], frozen="2026-10-05T08:31:00Z")
    _add_item(env["up_conn"], env["up_sid"], "https://e.com/n1", "新条目",
              fetched=datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc),
              content="新正文。")
    # 钟替身:t0=0;10-04 开始前=400(放行);10-05 开始前=800(预算尽)
    clock = iter(itertools.count(0, 400))

    code = _run_once(env, transport=_transport(
        env["config"], score_fail_marker="OLDFAIL", score_fail_status=400),
        monotonic=lambda: next(clock))

    # 旧期 10-04 评分 no_retry 全失败→E6 failed(可重试失败现在保存
    # 进度不落 failed,P1-6;此处用 400 保 E6 路径);10-05 预算耗尽
    # 未开始(保存状态)
    assert conn.execute("SELECT status, fail_reason FROM digest_issue WHERE"
                        " issue_date='2026-10-04'").fetchone()[1].startswith("E6")
    assert conn.execute("SELECT COUNT(*) FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == 0
    assert _attempts_for(conn, "2026-10-05") == 0
    # 新期保底:collect+生成+发布照常完成
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-06'").fetchone()[0] == "published"
    assert code == 3                                 # E6(旧期)优先于 0


# ---------- 验收 2:截止判定(锚点=frozen_utc 唯一) ----------

def test_deadline_d2_excludes_notifies_once_then_dedups(env):
    conn = env["conn"]
    _draft_row(conn, env["work"], "2026-10-03", [1], status="draft",
               frozen="2026-10-03T08:31:00Z")       # D=10-03
    code1 = _run_once(env, today="2026-10-05",
                      transport=_transport(env["config"]))
    # D+2:不自动开始+通知一次;新期无候选→no_candidates(3)
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-03'").fetchone()[0] == "draft"
    assert [k for k, _ in env["sent"]] == ["auto_expire:2026-10-03"]
    assert conn.execute("SELECT COUNT(*) FROM notify_sent").fetchone()[0] == 1
    assert code1 == 4                                 # 到期转人工(4)>3

    code2 = _run_once(env, today="2026-10-06",      # D+3 再跑:去重
                      transport=_transport(env["config"]))
    # auto_expire 去重保持 1 封;no_candidates 连续第 2 期(10-05 首期
    # 抑制)→二期通知发出(规则 7)
    assert [k for k, _ in env["sent"]] == ["auto_expire:2026-10-03",
                                           "no_candidates:2026-10-06"]
    assert conn.execute("SELECT COUNT(*) FROM notify_sent").fetchone()[0] == 2
    assert code2 == 4


def test_deadline_late_update_does_not_extend_eligibility(env):
    conn = env["conn"]
    # 晚状态更新:updated_utc 已到 D+1,但锚点仍是 frozen_utc(D 日)
    _draft_row(conn, env["work"], "2026-10-03", [1], status="draft",
               frozen="2026-10-03T08:31:00Z")
    with conn:
        conn.execute("UPDATE digest_issue SET updated_utc="
                     " '2026-10-04T23:00:00Z' WHERE issue_date='2026-10-03'")
    _run_once(env, today="2026-10-05", transport=_transport(env["config"]))
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-03'").fetchone()[0] == "draft"
    assert [k for k, _ in env["sent"]] == ["auto_expire:2026-10-03"]


def test_deadline_submitted_readonly_confirm_not_limited(env):
    # submitted 只读线上确认不受截止限制(D+2 仍确认→published)
    conn = env["conn"]
    _draft_row(conn, env["work"], "2026-10-03", [1], status="submitted",
               push=True, frozen="2026-10-03T08:31:00Z")
    _run_once(env, today="2026-10-05", transport=_transport(env["config"]))
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-03'").fetchone()[0] == "published"
    assert env["sent"] == []                         # 推进到终态不通知
    assert _attempts_for(conn, "2026-10-03") == 0    # 零费用


def test_deadline_d1_window_still_executes(env):
    conn = env["conn"]
    c = _entry(conn, "k-d1")
    _freeze(conn, "2026-10-04", [c], frozen="2026-10-04T08:31:00Z")
    _add_item(env["up_conn"], env["up_sid"], "https://e.com/n1", "新条目",
              fetched=datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc),
              content="新正文。")
    code = _run_once(env, today="2026-10-05",        # D+1 窗内:可跑完
                     transport=_transport(env["config"]))
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-04'").fetchone()[0] == "published"
    assert code == 0


# ---------- 验收 3:暂停置位→调度零动作;解除→状态不变仅恢复可见 ----------

def test_paused_issue_zero_actions_then_resumes_after_unpause(env):
    conn = env["conn"]
    c1 = _entry(conn, "k-p")
    _freeze(conn, "2026-10-05", [c1], frozen="2026-10-05T08:31:00Z",
            paused=1, reason="复核中")

    code = _run_once(env, transport=_transport(env["config"]))
    # 置位→零动作:无 attempt、entry 不动、无 digest_issue 行
    assert _attempts_for(conn, "2026-10-05") == 0
    assert conn.execute("SELECT status FROM entry WHERE identity_key='k-p'"
                        ).fetchone()[0] == "pending"
    assert conn.execute("SELECT COUNT(*) FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == 0
    assert code == 3                                 # 存量暂停零动作;新期 no_candidates

    with conn:                                       # 解除(只恢复可见性)
        conn.execute("UPDATE issue_freeze SET paused=0, paused_reason=NULL,"
                     " paused_utc=NULL WHERE issue_date='2026-10-05'")
    code2 = _run_once(env, today="2026-10-06",
                      transport=_transport(env["config"]))
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == "published"
    assert code2 == 0              # 2026-10-06 已 failed 不重跑(规则 5),
                                    # 唯一动作=2026-10-05 published


def test_paused_today_issue_skips_generation(env):
    # W1:当天期被暂停→不生成(退出码 4),零付费调用
    conn = env["conn"]
    c = _entry(conn, "k-today")
    _freeze(conn, "2026-10-06", [c], frozen="2026-10-06T08:31:00Z",
            paused=1, reason="撤回防护")
    events = []
    code = _run_once(env, transport=_transport(env["config"]),
                     events=events.append)
    assert code == 4
    assert _attempts_for(conn, "2026-10-06") == 0
    assert conn.execute("SELECT COUNT(*) FROM digest_issue WHERE"
                        " issue_date='2026-10-06'").fetchone()[0] == 0
    assert "phase:new:2026-10-06" not in events
    assert [k for k, _ in env["sent"]] == ["W1:2026-10-06"]  # 立即类通知


# ---------- 验收 4:failed 重跑=续跑(冻结/回执复用);放弃=释放占用 ----------

def test_rerun_failed_reuses_freeze_and_receipts(env):
    conn = env["conn"]
    b = _entry(conn, "k-rerun", title="重跑B")
    _freeze(conn, "2026-10-05", [b], frozen="2026-10-05T08:31:00Z")
    frozen_before = conn.execute(
        "SELECT frozen_utc FROM issue_freeze WHERE issue_date='2026-10-05'"
    ).fetchone()[0]
    # 第一次:双分成功但低于阈值→zero_qualified failed(P1-6 后可重试
    # 失败保存进度不落 failed,failed 落库走内容性失败路径)
    code = _run_once(env, today="2026-10-05",
                     transport=_transport(env["config"], score=10))
    row = conn.execute("SELECT status, fail_reason FROM digest_issue WHERE"
                       " issue_date='2026-10-05'").fetchone()
    assert row[0] == "failed" and row[1] == "zero_qualified"
    assert code == 3

    # 人工核对后 force_include → 重跑:续跑语义,冻结不重建
    with conn:
        conn.execute("INSERT INTO override (identity_key, action, created_utc)"
                     " VALUES ('k-rerun', 'force_include', ?)",
                     (NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),))
    code2 = rerun_issue(conn, env["config"], "2026-10-05",
                        publish_ctx=env["ctx"],
                        transport=_transport(env["config"]), now=NOW)
    # published;两条评分回执复用零新增 attempt;摘要 1 次
    assert conn.execute("SELECT frozen_utc FROM issue_freeze WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == \
        frozen_before
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == "published"
    rows = conn.execute(
        "SELECT r.purpose, COUNT(*) FROM receipt r JOIN receipt_attempt a"
        " ON a.receipt_id=r.id WHERE a.issue_date='2026-10-05'"
        " GROUP BY r.purpose ORDER BY r.purpose").fetchall()
    assert rows == [("score", 2), ("understand", 1)]
    assert code2 == 0


def test_abandon_failed_releases_claims_keeps_used(env, caplog):
    conn = env["conn"]
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, status,"
            " created_utc, fail_reason) VALUES ('2026-10-05', '[]',"
            " 'failed', '2026-10-05T09:00:00Z', 'E6.all_failed')")
    _entry(conn, "k-sel", status="selected", claim="2026-10-05")
    _entry(conn, "k-used", status="used", claim=None)

    with caplog.at_level(logging.INFO, logger="nanmu_engine.run"):
        abandon_issue(conn, "2026-10-05", reason="放弃该期")
    # claim 清+回 scored;used 不动;digest_issue 保持 failed(历史)
    assert conn.execute("SELECT status, claim_issue FROM entry WHERE"
                        " identity_key='k-sel'").fetchone() == ("scored", None)
    assert conn.execute("SELECT status FROM entry WHERE"
                        " identity_key='k-used'").fetchone()[0] == "used"
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == "failed"
    assert any("abandon" in r.message for r in caplog.records)


# ---------- 验收 5/退出码:字段映射与优先级聚合 ----------

def test_e2_collect_failure_lands_failed_row_with_last_exit(env):
    conn = env["conn"]
    code = _run_once(env, upstream=str(env["tmp_path"] / "missing.db"),
                     transport=_transport(env["config"]))
    row = conn.execute(
        "SELECT status, fail_reason, last_exit, last_run_utc FROM"
        " digest_issue WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == "failed" and row[1].startswith("E2")
    assert row[2] == 3 and row[3]                   # 收尾字段可查(§3 规则 6)
    assert code == 3


def test_zero_qualified_lands_failed_no_file(env):
    conn = env["conn"]
    _add_item(env["up_conn"], env["up_sid"], "https://e.com/low", "低分条目",
              fetched=datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc),
              content="正文。")
    code = _run_once(env, transport=_transport(env["config"], score=10))
    row = conn.execute("SELECT status, fail_reason, markdown_path FROM"
                       " digest_issue WHERE issue_date='2026-10-06'"
                       ).fetchone()
    assert row[0] == "failed" and row[1] == "zero_qualified"
    assert not (env["work"] / DIGEST_DIR / "2026-10-06.md").exists()
    assert code == 3


def test_exit_priority_isolation_over_new_issue_success(env):
    conn = env["conn"]
    # 副本塞他期未推送提交→10-05 发布与 10-06 发布均被隔离拦;生成照常
    path = env["work"] / DIGEST_DIR / "2026-10-04.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# 2026-10-04\n", encoding="utf-8")
    _run(["add", "."], env["work"])
    _run(["commit", "-m", "foreign", "-q"], env["work"])
    _draft_row(conn, env["work"], "2026-10-05", [1], status="draft",
               frozen="2026-10-05T08:31:00Z")
    _add_item(env["up_conn"], env["up_sid"], "https://e.com/n1", "新条目",
              fetched=datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc),
              content="新正文。")

    code = _run_once(env, transport=_transport(env["config"]))
    st = _statuses(conn)
    assert st == {"2026-10-05": "draft", "2026-10-06": "draft"}  # 两期均转人工(E8)
    assert conn.execute("SELECT COUNT(*) FROM summary").fetchone()[0] >= 1
    assert [k for k, _ in env["sent"]] == ["E8:2026-10-05", "E8:2026-10-06"]
    assert code == 4                                 # 4 优先于 0


def test_pay_paused_skips_new_paid_but_readonly_recovers(env):
    conn = env["conn"]
    with conn:
        conn.execute("UPDATE engine_meta SET value='1' WHERE"
                     " key='pay_paused'")
    c1 = _entry(conn, "k-sub2", status="selected", claim="2026-10-03")
    _draft_row(conn, env["work"], "2026-10-03", [c1["entry_id"]],
               status="submitted", push=True, frozen="2026-10-03T08:31:00Z")
    g = _entry(conn, "k-gen2")
    _freeze(conn, "2026-10-05", [g], frozen="2026-10-05T08:31:00Z")
    _add_item(env["up_conn"], env["up_sid"], "https://e.com/n1", "新条目",
              fetched=datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc),
              content="新正文。")

    code = _run_once(env, transport=_transport(env["config"]))
    # 只读/零费用步骤照常:submitted 恢复 published;collect 冻结照常
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-03'").fetchone()[0] == "published"
    assert conn.execute("SELECT COUNT(*) FROM issue_freeze WHERE"
                        " issue_date='2026-10-06'").fetchone()[0] == 1
    # 新增付费全部跳过:无 attempt、生成中期不落 failed(留待解除)
    assert _attempts_for(conn, "2026-10-05") == 0
    assert _attempts_for(conn, "2026-10-06") == 0
    assert conn.execute("SELECT COUNT(*) FROM digest_issue WHERE"
                        " issue_date IN ('2026-10-05','2026-10-06')"
                        ).fetchone()[0] == 0
    assert code == 4


def test_failed_issue_with_freeze_not_in_recovery(env):
    # 评分全挂落 failed 后冻结行仍在(常态)→ 该期不进自动恢复清单:
    # 零事件零新增 attempt;failed 只经人工 rerun(§3 规则 5)
    conn = env["conn"]
    m = _entry(conn, "k-failed1")
    _freeze(conn, "2026-10-05", [m], frozen="2026-10-05T08:31:00Z")
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, status,"
            " created_utc, fail_reason) VALUES ('2026-10-05', '[]',"
            " 'failed', '2026-10-05T09:00:00Z', 'E6.all_failed')")
    events = []
    _run_once(env, transport=_transport(env["config"]), events=events.append)
    assert "phase:recover:2026-10-05" not in events      # 不进恢复清单
    assert _attempts_for(conn, "2026-10-05") == 0        # 零新增 attempt
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == "failed"


def test_e1_config_error_notifies_immediately(env):
    # 修复轮 I5:配置错误(E1)=立即通知类(scheduling-ops 规则 7);
    # 零出网零 attempt
    bad = dataclasses.replace(env["config"], prompts=dataclasses.replace(
        env["config"].prompts,
        score=dataclasses.replace(env["config"].prompts.score,
                                  text="x" * 2_000_000)))
    code = run_once(env["conn"], bad,
                    upstream_path=env["upstream_path"], publish_ctx=env["ctx"],
                    transport=_transport(env["config"]), now=NOW,
                    today="2026-10-06", notify_send=env["sender"])
    assert code == 2
    assert _attempts_for(env["conn"], "2026-10-06") == 0
    assert [k for k, _ in env["sent"]] == ["E1.config:2026-10-06"]


def test_monthly_warning_fires_once_when_over_threshold(env):
    # 修复轮 I5:¥40 月度预警(warn_monthly)同月一封;阈值降低后当月
    # 已用(有成功期费用)即触发
    conn = env["conn"]
    _add_item(env["up_conn"], env["up_sid"], "https://e.com/w1", "预警条目",
              fetched=datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc),
              content="预警正文。")
    assert _run_once(env, transport=_transport(env["config"])) == 0
    assert env["sent"] == []                       # 成功期零通知
    low = dataclasses.replace(env["config"], budget=dataclasses.replace(
        env["config"].budget, warn_monthly_micro_cny=1))
    code = _run_once(env, transport=_transport(env["config"]),
                     config_override=None) if False else run_once(
        conn, low, upstream_path=env["upstream_path"], publish_ctx=env["ctx"],
        transport=_transport(env["config"]), now=NOW, today="2026-10-06",
        notify_send=env["sender"])
    assert code == 0
    assert [k for k, _ in env["sent"]] == ["warn-monthly:2026-10"]
    # 同月再跑:去重一封
    run_once(conn, low, upstream_path=env["upstream_path"],
             publish_ctx=env["ctx"], transport=_transport(env["config"]),
             now=NOW, today="2026-10-06", notify_send=env["sender"])
    assert len(env["sent"]) == 1


# ---------- R2(P1-2/P1-6):身份贯穿/续跑语义/单条隔离 ----------

def test_zero_n_new_run_publishes_from_pure_reuse(env):
    """R2:评分+摘要回执齐后崩溃,续跑日预算停用(compute_n_new=0)——
    完整请求身份贯穿复用判定,纯复用照常发布,零新增付费调用。"""
    from nanmu_engine.score import score_entry
    from nanmu_engine.summarize import understand_entry
    conn = env["conn"]
    c = _entry(conn, "k-reuse")
    _freeze(conn, "2026-10-05", [c], frozen="2026-10-05T08:31:00Z")
    score_entry(conn, env["config"], c, issue_date="2026-10-05",
                transport=_transport(env["config"]), now=NOW)
    understand_entry(conn, env["config"], c, issue_date="2026-10-05",
                     transport=_transport(env["config"]), now=NOW)
    n_before = _attempts_for(conn, "2026-10-05")
    assert n_before == 3                        # score×2 + understand×1

    disabled = dataclasses.replace(env["config"], budget=dataclasses.replace(
        env["config"].budget, monthly_micro_cny=0))   # 合法停用→N_new=0
    from nanmu_engine.ledger import compute_n_new
    assert compute_n_new(conn, disabled, "2026-10-06", now=NOW) == 0

    code = run_once(conn, disabled, upstream_path=env["upstream_path"],
                    publish_ctx=env["ctx"], transport=_transport(env["config"]),
                    now=NOW, today="2026-10-06", notify_send=env["sender"])
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == "published"
    assert _attempts_for(conn, "2026-10-05") == n_before   # 零新增
    assert code == 3                            # 当天新期 no_candidates


def test_retryable_failures_save_progress_not_failed(env):
    """R2:候选两次评分均为可重试失败(E3.http 500)且名额未尽——保存
    进度留待下次调度续跑,不落 failed(failed 不自动恢复会冻结重试承诺)。"""
    conn = env["conn"]
    c = _entry(conn, "k-retry")
    _freeze(conn, "2026-10-05", [c], frozen="2026-10-05T08:31:00Z")
    fail_all = httpx.MockTransport(
        lambda req: httpx.Response(500, json={"error": "boom"}))

    code = _run_once(env, transport=fail_all)
    assert conn.execute("SELECT COUNT(*) FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == 0
    assert code == 4                            # 保存续接,非期失败
    assert _attempts_for(conn, "2026-10-05") == 2

    code2 = _run_once(env, transport=_transport(env["config"]))
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == "published"
    # score 每侧重试 1 次(2+2)+ understand 1 次 = 5
    assert _attempts_for(conn, "2026-10-05") == 5


def test_title_too_long_member_isolated(env):
    """R2:超长标题成员在预筛前截断即抛 title_too_long——按单条规则剔除
    该成员,不中断整期(正常成员照常发布)。"""
    conn = env["conn"]
    bad = _entry(conn, "k-longtitle", title="超" * 5000)
    ok = _entry(conn, "k-oktitle")
    _freeze(conn, "2026-10-05", [bad, ok], frozen="2026-10-05T08:31:00Z")

    code = _run_once(env, transport=_transport(env["config"]))
    assert code == 3                            # 当天新期 no_candidates
    assert conn.execute("SELECT status FROM digest_issue WHERE"
                        " issue_date='2026-10-05'").fetchone()[0] == "published"
    assert conn.execute("SELECT status FROM entry WHERE"
                        " identity_key='k-oktitle'").fetchone()[0] == "used"
    assert conn.execute("SELECT status FROM entry WHERE"
                        " identity_key='k-longtitle'").fetchone()[0] == "pending"
    # 超长标题零付费调用;正常成员 score×2+understand×1
    assert _attempts_for(conn, "2026-10-05") == 3


def test_changed_entry_body_rescored_not_reusing_old_analysis(env):
    """R2:上游重抓同身份条目正文变化 → 新请求身份重评分;运行层不得
    借旧 analysis 行读旧分数(高分洗白/重复入围旧输入)。"""
    conn = env["conn"]
    from nanmu_engine.score import score_entry
    c = _entry(conn, "k-chg", body="旧正文内容")
    score_entry(conn, env["config"], c, issue_date="2026-10-05",
                transport=_transport(env["config"], score=90), now=NOW)

    # 上游重抓:同 url 新正文 → 2026-10-06 新期按新输入评分(替身返回 10)
    _add_item(env["up_conn"], env["up_sid"], c["url"], "重抓条目",
              fetched=datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc),
              content="旧正文内容")
    with env["up_conn"]:
        env["up_conn"].execute(
            "UPDATE item SET content_text=?, fetched_utc=? WHERE url=?",
            ("重抓后的全新正文", "2026-10-06T07:00:00Z", c["url"]))

    code = _run_once(env, transport=_transport(env["config"], score=10))
    row = conn.execute("SELECT status, fail_reason FROM digest_issue WHERE"
                       " issue_date='2026-10-06'").fetchone()
    assert row[0] == "failed" and row[1] == "zero_qualified"   # 新分 10<T1 60
    assert conn.execute("SELECT status FROM entry WHERE"
                        " identity_key='k-chg'").fetchone()[0] != "used"
    rows = conn.execute("SELECT score_1 FROM analysis ORDER BY id").fetchall()
    assert [r[0] for r in rows] == [90, 10]     # 新输入=新行,旧行保留
