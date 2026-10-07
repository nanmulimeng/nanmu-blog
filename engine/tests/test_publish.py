"""发布链测试:四窗口恢复、隔离检查、线上证据链三步、ops_json 协议。
种子=publish-withdraw 验收 1/2/3/8;本地 bare repo 夹具模拟远端,禁止真实
push 出网;恢复路径零 LLM(receipt_attempt 计数断言)。"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from nanmu_engine.assemble import DigestDraft, write_draft
from nanmu_engine.config import load_config
from nanmu_engine.db import connect_db, migrate
from nanmu_engine.publish import (
    ManualIntervention,
    PublishContext,
    append_op,
    confirm_op,
    correct,
    publish_issue,
    recover_content_op,
    recover_issue,
    relist,
    stale_cost_issues,
    update_op_stage,
    visible_status,
    withdraw,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]
DIGEST_DIR = "site/src/content/digest"


def _run(args, cwd, check=True, binary=False):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                       text=not binary)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args}: {r.stderr or r.stdout}")
    return r.stdout if binary else r.stdout.strip()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    state = {"url_ok": True}

    def release_sha():
        return _run(["rev-parse", "origin/main"], work) or None

    ctx = PublishContext(
        workdir=work, remote_url=str(remote), branch="main",
        digest_dir=DIGEST_DIR, site_base="https://blog.example",
        fetch_release_sha=release_sha,
        fetch_url_ok=lambda url: state["url_ok"])
    return conn, config, ctx, work, state


def _digest_path(work, issue_date):
    p = work / DIGEST_DIR / f"{issue_date}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _make_draft(conn, work, issue_date="2026-10-06", entry_ids=(100,)):
    md = ("---\ndate: '%s'\ngenerated: true\nai_model: m\nentry_count: 1\n"
          "cost_cny: 0.01\ncost_pending: false\n---\n\n## 值得一瞥(压线入选)"
          "\n\n- [t](https://e.com)(s · 展示分 71)——p\n" % issue_date)
    path = _digest_path(work, issue_date)
    path.write_text(md, encoding="utf-8")
    sha = hashlib.sha256(md.encode("utf-8")).hexdigest()
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, markdown_path,"
            " content_sha256, cost_cny, status, created_utc, updated_utc)"
            " VALUES (?,?,?,?,?, 'draft', '2026-10-06T00:00:00Z',"
            " '2026-10-06T00:00:00Z')",
            (issue_date, json.dumps(list(entry_ids)), str(path), sha, 0.01))
    return sha, path


def _seed_claim(conn, key, *, status="selected", claim="2026-10-06",
                entry_id=None, url="https://e.com"):
    cur = conn.execute(
        "INSERT INTO entry (identity_key, url, title, source_name,"
        " source_tier, discovered_utc, content_text, status, claim_issue)"
        " VALUES (?, ?, 't', 'src', 'T1',"
        " '2026-10-06T00:00:00Z', 'b', ?, ?)",
        (key, url, status, claim))
    conn.commit()
    return entry_id or cur.lastrowid


def _commit_file(work, issue_date, content=None):
    path = _digest_path(work, issue_date)
    if content is not None:
        path.write_text(content, encoding="utf-8")
    elif not path.exists():
        path.write_text(f"# {issue_date}\n", encoding="utf-8")
    _run(["add", "."], work)
    _run(["commit", "-m", f"digest {issue_date}", "-q"], work)
    return _run(["rev-parse", "HEAD"], work)


def _entry_states(conn):
    return conn.execute(
        "SELECT identity_key, status, claim_issue FROM entry"
        " ORDER BY identity_key").fetchall()


def _attempts(conn):
    return conn.execute("SELECT COUNT(*) FROM receipt_attempt").fetchone()[0]


# ---------- 验收 1:发布推进 + published 与清算同事务 ----------

def test_publish_promotes_and_settles_same_transaction(env):
    conn, config, ctx, work, state = env
    sha, _ = _make_draft(conn, work)
    _seed_claim(conn, "in1")                       # 进最终产物
    _seed_claim(conn, "in2")
    _seed_claim(conn, "out1")                      # 中间暂离(裁剪/剔除)

    res = publish_issue(conn, "2026-10-06", ctx,
                        final_keys=["in1", "in2"])
    assert res.status == "published"
    row = conn.execute(
        "SELECT status, git_commit, content_sha256 FROM digest_issue"
        " WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == "published" and row[1] and row[2] == sha
    # 进产物 used+claim 清;未进 rejected+claim 清(无混合事实)
    assert _entry_states(conn) == [
        ("in1", "used", None), ("in2", "used", None),
        ("out1", "rejected", None)]
    # 远端已接收且树内文件身份=库内 content_sha256
    _run(["fetch", "origin"], work)
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", row[1], "origin/main"],
        cwd=str(work), capture_output=True)
    assert r.returncode == 0
    blob = _run(["show", f"{row[1]}:{DIGEST_DIR}/2026-10-06.md"], work,
                binary=True)
    assert hashlib.sha256(blob).hexdigest() == sha


def test_publish_without_online_evidence_stays_submitted(env):
    # 验收 8 反例前提:线上证据不可得 → 保持 submitted 只重查
    conn, config, ctx, work, state = env
    _make_draft(conn, work)
    _seed_claim(conn, "in1")
    state["url_ok"] = False                        # URL 404
    res = publish_issue(conn, "2026-10-06", ctx, final_keys=["in1"])
    assert res.status == "submitted"
    st = conn.execute("SELECT status FROM digest_issue"
                      " WHERE issue_date='2026-10-06'").fetchone()[0]
    assert st == "submitted"
    assert _entry_states(conn) == [("in1", "selected", "2026-10-06")]  # 未清算


# ---------- 验收 2:四窗口 W1-W4(kill 注入 → 只补记不重生成) ----------

def test_w1_commit_without_db_row_backfills_draft(env):
    conn, config, ctx, work, state = env
    before = _attempts(conn)
    eid = _seed_claim(conn, "in1")                 # 期成员(claim 在)
    # 产物含成员来源 URL(回填以产物内容为事实,见 B-缝A)
    sha = _commit_file(work, "2026-10-06",
                       content=f"# 2026-10-06\n\n- [t](https://e.com)——p\n")
    out = recover_issue(conn, "2026-10-06", ctx)
    assert out.status == "draft"
    row = conn.execute(
        "SELECT status, git_commit, content_sha256, entry_ids FROM"
        " digest_issue WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == "draft" and row[1] == sha     # 复用提交不重组
    blob = _run(["show", f"{sha}:{DIGEST_DIR}/2026-10-06.md"], work,
                binary=True)
    assert row[2] == hashlib.sha256(blob).hexdigest()
    assert json.loads(row[3]) == [eid]             # 成员从 claim 反查,非 '[]'
    assert _attempts(conn) == before               # 零评分调用


def test_w2_sha_backfill_ignores_dirty_workdir(env):
    conn, config, ctx, work, state = env
    sha, path = _make_draft(conn, work)            # draft 行在、git_commit 空
    commit = _commit_file(work, "2026-10-06")
    path.write_text("人为改动后的工作副本", encoding="utf-8")  # 现场污染
    out = recover_issue(conn, "2026-10-06", ctx)
    assert out.status == "draft"
    row = conn.execute("SELECT git_commit, content_sha256, status"
                       " FROM digest_issue WHERE issue_date='2026-10-06'"
                       ).fetchone()
    # 以库内 content_sha256 在 git 历史找到提交,不受副本现状影响
    assert row[0] == commit and row[1] == sha and row[2] == "draft"


def test_w2_lookup_failure_goes_manual(env):
    conn, config, ctx, work, state = env
    _make_draft(conn, work)                        # 库内身份无对应提交
    with pytest.raises(ManualIntervention, match="证据不足"):
        recover_issue(conn, "2026-10-06", ctx)


def test_w3_ancestor_judges_submitted(env):
    conn, config, ctx, work, state = env
    sha, _ = _make_draft(conn, work)
    commit = _commit_file(work, "2026-10-06")
    _run(["push", "origin", "main"], work)         # push 成功、状态仍 draft
    with conn:
        conn.execute("UPDATE digest_issue SET git_commit=? WHERE"
                     " issue_date='2026-10-06'", (commit,))
    out = recover_issue(conn, "2026-10-06", ctx)
    assert out.status == "submitted"


def test_w3_sha_reachable_but_not_ancestor_stays_draft(env):
    # ls-remote 只示尖端:SHA 在 origin/deploy 可达但非 origin/main 祖先
    conn, config, ctx, work, state = env
    _make_draft(conn, work)
    commit = _commit_file(work, "2026-10-06")
    _run(["push", "origin", f"{commit}:refs/heads/deploy"], work)
    with conn:
        conn.execute("UPDATE digest_issue SET git_commit=? WHERE"
                     " issue_date='2026-10-06'", (commit,))
    out = recover_issue(conn, "2026-10-06", ctx)
    assert out.status == "draft"                   # 不判 submitted


def test_w4_online_confirms_published_and_settles_idempotent(env):
    conn, config, ctx, work, state = env
    in1 = _seed_claim(conn, "in1")
    _seed_claim(conn, "out1")
    sha, _ = _make_draft(conn, work, entry_ids=(in1,))
    commit = _commit_file(work, "2026-10-06")
    _run(["push", "origin", "main"], work)
    with conn:
        conn.execute(
            "UPDATE digest_issue SET git_commit=?, status='submitted'"
            " WHERE issue_date='2026-10-06'", (commit,))
    out = recover_issue(conn, "2026-10-06", ctx)
    assert out.status == "published"
    assert _entry_states(conn) == [("in1", "used", None),
                                   ("out1", "rejected", None)]
    # 幂等:重复恢复不重复置 used / 不重复推进
    out2 = recover_issue(conn, "2026-10-06", ctx)
    assert out2.status == "published"
    assert _entry_states(conn) == [("in1", "used", None),
                                   ("out1", "rejected", None)]


def test_w4_online_path_404_not_published(env):
    # 验收 8:线上 SHA 含提交但路径 404(后续提交删除)→ 不判 published
    conn, config, ctx, work, state = env
    sha, _ = _make_draft(conn, work)
    commit = _commit_file(work, "2026-10-06")
    _run(["push", "origin", "main"], work)
    _seed_claim(conn, "in1")
    with conn:
        conn.execute(
            "UPDATE digest_issue SET git_commit=?, status='submitted'"
            " WHERE issue_date='2026-10-06'", (commit,))
    state["url_ok"] = False                        # 模拟路径 404
    out = recover_issue(conn, "2026-10-06", ctx)
    assert out.status == "submitted"


# ---------- 验收 3:跨期工作副本隔离检查 ----------

def test_isolation_blocks_push_with_other_issue_commits(env):
    conn, config, ctx, work, state = env
    _commit_file(work, "2026-10-05")               # 他期未推送提交
    _make_draft(conn, work, "2026-10-06")
    _seed_claim(conn, "in1")
    with pytest.raises(ManualIntervention, match="隔离|他期|isolation"):
        publish_issue(conn, "2026-10-06", ctx, final_keys=["in1"])
    # 远端未收到新期产物
    assert "2026-10-06.md" not in _run(
        ["ls-tree", "-r", "--name-only", "origin/main"], work)
    # 清理他期提交后正常发布
    _run(["reset", "--hard", "origin/main"], work)
    res = publish_issue(conn, "2026-10-06", ctx, final_keys=["in1"])
    assert res.status == "published"


# ---------- ops_json 协议(规则 5;撤回/重上/纠错序列由后续任务消费) ----------

def test_ops_json_append_stage_confirm_and_visible_status(env):
    conn, config, ctx, work, state = env
    _make_draft(conn, work)
    assert visible_status(conn, "2026-10-06") == "draft"   # 无 op 按 status
    append_op(conn, "2026-10-06", "withdraw", "ABSENT")    # 操作开始即持久化
    append_op(conn, "2026-10-06", "relist", "sha-abc")
    ops = json.loads(conn.execute(
        "SELECT ops_json FROM digest_issue WHERE issue_date='2026-10-06'"
        ).fetchone()[0])
    assert [o["seq"] for o in ops] == [1, 2]
    assert all(o["stages"] == {} for o in ops)
    update_op_stage(conn, "2026-10-06", 2, "commit", "c1")
    update_op_stage(conn, "2026-10-06", 2, "pushed", "p1")
    confirm_op(conn, "2026-10-06", 2,
               confirmed_utc="2026-10-06T09:00:00Z")
    # 在线类确认同事务推进 content_sha256=该 op target
    assert conn.execute("SELECT content_sha256 FROM digest_issue WHERE"
                        " issue_date='2026-10-06'").fetchone()[0] == "sha-abc"
    assert visible_status(conn, "2026-10-06") == "relisted"
    # 再撤回:第二个 withdraw confirmed → 当前可见状态回到撤回(验收 4 反例)
    append_op(conn, "2026-10-06", "withdraw", "ABSENT")
    confirm_op(conn, "2026-10-06", 3,
               confirmed_utc="2026-10-06T10:00:00Z")
    assert visible_status(conn, "2026-10-06") == "withdrawn"


# ==================== Task 18:撤回/重新上线/纠错(验收 4/5/6/7) ====================

def _seed_attempt(conn, issue_date, micro):
    with conn:
        cur = conn.execute(
            "INSERT INTO receipt (logical_key, provider, endpoint,"
            " request_hash, service, purpose, model, status, request_digest,"
            " created_utc) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"lk{micro}-{issue_date}", "deepseek", "/chat/completions",
             "h1", "llm", "score", "m", "completed", "{}",
             "2026-10-06T00:00:00Z"))
        conn.execute(
            "INSERT INTO receipt_attempt (receipt_id, attempt_no,"
            " issue_date, started_utc, status, attempt_origin,"
            " reserved_micro_cny, actual_micro_cny, pricing_version)"
            " VALUES (?,1,?,'2026-10-06T01:00:00Z','received','initial',"
            " ?,?, 'v1')", (cur.lastrowid, issue_date, micro, micro))


def _publish_ok(conn, ctx, work, *, issue_date="2026-10-06", micro=10000):
    """把一期推到 published(含一条已结算 attempt 使行 cost=快照一致)。"""
    _seed_attempt(conn, issue_date, micro)
    in1 = _seed_claim(conn, "in1")
    sha, _ = _make_draft(conn, work, issue_date, entry_ids=(in1,))
    res = publish_issue(conn, issue_date, ctx, final_keys=["in1"])
    assert res.status == "published"
    return sha


def _withdraw_confirmed(conn, ctx, work, state, *, issue_date="2026-10-06"):
    state["url_ok"] = True                   # 期在线
    withdraw(conn, issue_date, ctx, reason="内容有误")
    state["url_ok"] = False                  # 部署生效:三处消失
    out = recover_content_op(conn, issue_date, ctx)
    assert out == "withdrawn"


def test_withdraw_full_sequence_pause_and_rewithdraw(env):
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    state["url_ok"] = True
    res = withdraw(conn, "2026-10-06", ctx, reason="内容有误")
    assert res.status == "pending"           # push 完成,线上未消失
    row = conn.execute(
        "SELECT status, withdrawn_utc, withdraw_commit FROM digest_issue"
        " WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == "published"             # status 保持=历史事实
    assert row[1] is None                    # 未确认不落两列
    tip = _run(["rev-parse", "origin/main"], work)
    assert _run(["ls-tree", tip, f"{DIGEST_DIR}/2026-10-06.md"], work) == ""
    # 暂停置位(重启后无自动重发)
    assert conn.execute("SELECT paused, paused_reason FROM issue_freeze"
                        " WHERE issue_date='2026-10-06'"
                        ).fetchone() == (1, "内容有误")
    state["url_ok"] = False
    out = recover_content_op(conn, "2026-10-06", ctx)
    assert out == "withdrawn"
    row = conn.execute(
        "SELECT withdrawn_utc, withdraw_commit FROM digest_issue"
        " WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] and row[1]
    assert visible_status(conn, "2026-10-06") == "withdrawn"


def test_relist_verbatim_restores_parent_version_zero_llm(env):
    conn, config, ctx, work, state = env
    old_sha = _publish_ok(conn, ctx, work)
    _withdraw_confirmed(conn, ctx, work, state)
    state["url_ok"] = True                   # 重上后线上恢复
    before = _attempts(conn)
    res = relist(conn, "2026-10-06", ctx, mode="verbatim")
    assert res.status == "relisted"
    assert _attempts(conn) == before         # 零模型调用
    row = conn.execute(
        "SELECT content_sha256, relisted_utc, relist_commit, withdrawn_utc"
        " FROM digest_issue WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == old_sha                 # 恢复身份=撤回父版本
    assert row[1] and row[2]
    assert row[3]                            # 撤回史实保留
    assert visible_status(conn, "2026-10-06") == "relisted"
    tip = _run(["rev-parse", "origin/main"], work)
    blob = _run(["show", f"{tip}:{DIGEST_DIR}/2026-10-06.md"], work,
                binary=True)
    assert hashlib.sha256(blob).hexdigest() == old_sha


def test_relist_corrected_target_persisted_before_network(env):
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    _withdraw_confirmed(conn, ctx, work, state)
    state["url_ok"] = False                  # push 后部署前 kill
    new_md = ("---\ndate: '2026-10-06'\ngenerated: true\nai_model: m\n"
              "entry_count: 2\ncost_cny: 0.01\ncost_pending: false\n---\n"
              "\n## 值得一瞥(压线入选)\n\n- [修正](https://e.com)"
              "(s · 展示分 71)——p\n")
    res = relist(conn, "2026-10-06", ctx, mode="corrected",
                 corrected_content=new_md)
    assert res.status == "pending"
    ops = json.loads(conn.execute(
        "SELECT ops_json FROM digest_issue WHERE issue_date='2026-10-06'"
        ).fetchone()[0])
    last = ops[-1]
    target = hashlib.sha256(new_md.encode("utf-8")).hexdigest()
    assert last["op"] == "relist_corrected"
    assert last["target_sha256"] == target   # 目标版本在出网前已持久化
    assert not last["stages"].get("confirmed_utc")
    state["url_ok"] = True                   # 重启:线上已恢复
    out = recover_content_op(conn, "2026-10-06", ctx)
    assert out == "relisted"
    row = conn.execute(
        "SELECT content_sha256, relisted_utc, relist_commit FROM"
        " digest_issue WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == target
    assert row[1] and row[2]


def test_content_op_recovery_insufficient_evidence_goes_manual(env):
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    _withdraw_confirmed(conn, ctx, work, state)
    append_op(conn, "2026-10-06", "relist", "deadbeef")  # target 无匹配提交
    state["url_ok"] = True
    with pytest.raises(ManualIntervention, match="证据不足"):
        recover_content_op(conn, "2026-10-06", ctx)


def test_rewithdraw_after_relist_visible_is_withdrawn(env):
    # 验收 4 反例:撤回→重上→再撤,当前可见=撤回;relisted 列不参与判定
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    _withdraw_confirmed(conn, ctx, work, state)
    state["url_ok"] = True
    relist(conn, "2026-10-06", ctx, mode="verbatim")
    assert visible_status(conn, "2026-10-06") == "relisted"
    _withdraw_confirmed(conn, ctx, work, state)           # 再撤回
    assert visible_status(conn, "2026-10-06") == "withdrawn"
    row = conn.execute(
        "SELECT relisted_utc, withdrawn_utc FROM digest_issue"
        " WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] and row[1]                 # 两类史实均在,判定只看 op


def test_correct_replaces_content_keeps_history(env):
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    old_commit = conn.execute(
        "SELECT git_commit FROM digest_issue WHERE issue_date='2026-10-06'"
        ).fetchone()[0]
    fixed = ("---\ndate: '2026-10-06'\ngenerated: true\nai_model: m\n"
             "entry_count: 3\ncost_cny: 0.01\ncost_pending: false\n---\n"
             "\n## 值得一瞥(压线入选)\n\n- [纠错版](https://e.com)"
             "(s · 展示分 71)——p\n")
    res = correct(conn, "2026-10-06", ctx, new_content=fixed)
    assert res.status == "corrected"
    new_sha = hashlib.sha256(fixed.encode("utf-8")).hexdigest()
    row = conn.execute(
        "SELECT content_sha256, status FROM digest_issue"
        " WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == new_sha and row[1] == "published"
    assert "entry_count: 3" in fixed          # entry_count 如实变化
    _run(["fetch", "origin"], work)
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", old_commit, "origin/main"],
        cwd=str(work), capture_output=True)
    assert r.returncode == 0                  # 历史保留


def test_stale_cost_issues_after_settlement_change(env):
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)             # 行 cost=快照=0.01
    assert stale_cost_issues(conn) == []
    _seed_attempt(conn, "2026-10-06", 20000)  # 核清后快照变化→0.03
    stale = stale_cost_issues(conn)
    assert [s["issue_date"] for s in stale] == ["2026-10-06"]
    assert stale[0]["snapshot_cost_cny"] == pytest.approx(0.03)
    # 更新走纠错式提交(此处模拟三处一致后)→清单清空
    with conn:
        conn.execute("UPDATE digest_issue SET cost_cny=0.03 WHERE"
                     " issue_date='2026-10-06'")
    assert stale_cost_issues(conn) == []


# ==================== 审计修复轮 P1-4/P1-5:证据链与提交隔离 ====================

def test_publish_ff_syncs_when_workdir_behind_remote(env, tmp_path):
    # P1-5:本地落后远端(他处已推送)→ 必须 fast-forward 同步后再提交,
    # 否则后续 push 非快进失败
    conn, config, ctx, work, state = env
    _make_draft(conn, work)
    _seed_claim(conn, "in1")
    other = tmp_path / "other"
    _run(["clone", ctx.remote_url, str(other)], tmp_path)
    _run(["config", "user.email", "t@t"], other)
    _run(["config", "user.name", "t"], other)
    (other / "README.md").write_text("site v2", encoding="utf-8")
    _run(["add", "."], other)
    _run(["commit", "-m", "elsewhere", "-q"], other)
    _run(["push", "origin", "main"], other)        # 远端前进,work 落后

    res = publish_issue(conn, "2026-10-06", ctx, final_keys=["in1"])
    assert res.status == "published"               # ff 同步→提交→push 成功


def test_publish_ignores_staged_foreign_files(env):
    # P1-5:暂存区的无关文件不得被日报提交一并带出(提交范围=pathspec)
    conn, config, ctx, work, state = env
    _make_draft(conn, work)
    _seed_claim(conn, "in1")
    (work / "foreign.txt").write_text("无关暂存", encoding="utf-8")
    _run(["add", "foreign.txt"], work)             # 暂存区有无关内容

    res = publish_issue(conn, "2026-10-06", ctx, final_keys=["in1"])
    assert res.status == "published"
    tip = _run(["rev-parse", "origin/main"], work)
    assert "foreign.txt" not in _run(
        ["ls-tree", "-r", "--name-only", tip], work)


def test_publish_refuses_when_worktree_identity_mismatch(env):
    # P1-5:提交前校验工作树文件身份=库内预期,被改动的日报不得提交
    conn, config, ctx, work, state = env
    sha, path = _make_draft(conn, work)
    _seed_claim(conn, "in1")
    tampered = ("---\ndate: '2026-10-06'\ngenerated: true\nai_model: m\n"
                "entry_count: 1\ncost_cny: 0.01\ncost_pending: false\n---\n"
                "\n## 被人改过的日报\n\n- [x](https://e.com)——p\n")
    path.write_text(tampered, encoding="utf-8")    # frontmatter 完好的改动
    with pytest.raises(ManualIntervention, match="身份|identity"):
        publish_issue(conn, "2026-10-06", ctx, final_keys=["in1"])
    # 无新提交,远端未收到
    assert _run(["rev-parse", "HEAD"], work) == \
        _run(["rev-parse", "origin/main"], work)


def test_correct_needs_deployed_sha_match_not_only_url(env):
    # P1-4:URL 可读(旧页本就可读)≠ 部署已吃进修正版;部署 SHA 树内
    # 身份≠target → 不 confirmed、content_sha256 不前进
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    stale_tip = _run(["rev-parse", "origin/main"], work)
    ctx.fetch_release_sha = lambda: stale_tip     # 部署停在纠错前
    fixed = ("---\ndate: '2026-10-06'\ngenerated: true\nai_model: m\n"
             "entry_count: 9\ncost_cny: 0.01\ncost_pending: false\n---\n"
             "\n## 值得一瞥\n\n- [x](https://e.com)(s · 展示分 71)——p\n")
    res = correct(conn, "2026-10-06", ctx, new_content=fixed)
    assert res.status == "pending"                 # 证据不足保持未确认
    old_sha = conn.execute("SELECT content_sha256 FROM digest_issue WHERE"
                           " issue_date='2026-10-06'").fetchone()[0]
    assert old_sha != hashlib.sha256(fixed.encode("utf-8")).hexdigest()
    ops = json.loads(conn.execute(
        "SELECT ops_json FROM digest_issue WHERE issue_date='2026-10-06'"
        ).fetchone()[0])
    assert not ops[-1]["stages"].get("confirmed_utc")


def test_withdraw_needs_deployment_evidence_not_only_404(env):
    # P1-4:URL 不可读(可能是网络抖/站点故障)≠ 撤回已部署;部署 SHA
    # 树内仍有该路径 → 不 confirmed、withdrawn_utc 不落
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    stale_tip = _run(["rev-parse", "origin/main"], work)
    ctx.fetch_release_sha = lambda: stale_tip     # 部署未吃掉删除
    state["url_ok"] = False
    res = withdraw(conn, "2026-10-06", ctx, reason="内容有误")
    assert res.status == "pending"
    row = conn.execute("SELECT withdrawn_utc, withdraw_commit FROM"
                       " digest_issue WHERE issue_date='2026-10-06'"
                       ).fetchone()
    assert row[0] is None


def test_w1_backfills_members_then_w4_settles_used(env):
    # P1-4:W1 补记 entry_ids 从 claim 反查;随后 W4 确认 published 时
    # 成员结算 used(不是 '[]' → 全员 rejected 丢"已发布使用"事实)
    conn, config, ctx, work, state = env
    in1 = _seed_claim(conn, "in1")
    sha = _commit_file(work, "2026-10-06",
                       content=f"# 2026-10-06\n\n- [t](https://e.com)——p\n")
    _run(["push", "origin", "main"], work)
    out = recover_issue(conn, "2026-10-06", ctx)   # W1
    assert out.status == "draft"
    ids = json.loads(conn.execute(
        "SELECT entry_ids FROM digest_issue WHERE issue_date='2026-10-06'"
        ).fetchone()[0])
    assert ids == [in1]
    with conn:
        conn.execute("UPDATE digest_issue SET git_commit=?, status="
                     " 'submitted' WHERE issue_date='2026-10-06'", (sha,))
    out2 = recover_issue(conn, "2026-10-06", ctx)  # W4
    assert out2.status == "published"
    assert _entry_states(conn) == [("in1", "used", None)]


def test_w1_without_claimed_members_goes_manual(env):
    # 无 claim 成员可回填 → 不写 '[]',转人工
    conn, config, ctx, work, state = env
    _commit_file(work, "2026-10-06")
    with pytest.raises(ManualIntervention, match="证据不足"):
        recover_issue(conn, "2026-10-06", ctx)


def test_content_op_unpushed_target_goes_manual(env):
    # P1-4:目标版本在本地历史但未被远端接收(push 中断)→ 证据不足
    # 转人工,不自动重提交、不凭 URL 可读确认
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    _withdraw_confirmed(conn, ctx, work, state)
    new_md = ("---\ndate: '2026-10-06'\ngenerated: true\nai_model: m\n"
              "entry_count: 2\ncost_cny: 0.01\ncost_pending: false\n---\n"
              "\n## 值得一瞥\n\n- [y](https://e.com)(s · 展示分 71)——p\n")
    _digest_path(work, "2026-10-06").write_text(new_md, encoding="utf-8")
    _run(["add", "."], work)
    _run(["commit", "-m", "digest(relist_corrected): 2026-10-06", "-q"], work)
    target = hashlib.sha256(new_md.encode("utf-8")).hexdigest()
    append_op(conn, "2026-10-06", "relist_corrected", target)  # 未推送
    state["url_ok"] = True                          # 旧页可读≠新版本已上线
    with pytest.raises(ManualIntervention, match="证据不足"):
        recover_content_op(conn, "2026-10-06", ctx)


# ==================== 交界核验轮(发布×账本/恢复) ====================

def test_w1_backfills_only_members_in_artifact(env):
    # 交界 B-缝A:W1 回填口径=最终产物成员(产物 markdown 含其完整来源
    # 链接目标),不是 claim 全集——被剔除成员不得借 W4 清算置 used(丧失
    # 后续期再入选资格)。
    # 复核 P2:URL 子串命中不算进产物——A 的 URL 是产物内 B 的 URL 的
    # 前缀("https://e.com/a" ⊂ "https://e.com/ab")时,A 不得被子串
    # 反解误恢复;须对产物链接目标集合做精确成员判定。
    conn, config, ctx, work, state = env
    _seed_claim(conn, "in1", url="https://e.com/a")     # 前缀陷阱:未进产物
    b_id = _seed_claim(conn, "out1", url="https://e.com/ab")  # 唯一进产物
    md = ("---\ndate: '2026-10-06'\ngenerated: true\nai_model: m\n"
          "entry_count: 1\ncost_cny: 0.01\ncost_pending: false\n---\n"
          "\n## 值得一瞥(压线入选)\n\n- [t](https://e.com/ab)"
          "(s · 展示分 71)——p\n")
    sha = _commit_file(work, "2026-10-06", content=md)
    _run(["push", "origin", "main"], work)
    out = recover_issue(conn, "2026-10-06", ctx)        # W1
    assert out.status == "draft"
    ids = json.loads(conn.execute(
        "SELECT entry_ids FROM digest_issue WHERE issue_date='2026-10-06'"
        ).fetchone()[0])
    assert ids == [b_id]                        # 只回填产物内成员(精确匹配)
    with conn:
        conn.execute("UPDATE digest_issue SET git_commit=?, status="
                     " 'submitted' WHERE issue_date='2026-10-06'", (sha,))
    out2 = recover_issue(conn, "2026-10-06", ctx)       # W4
    assert out2.status == "published"
    assert _entry_states(conn) == [("in1", "rejected", None),
                                   ("out1", "used", None)]


def test_w1_member_count_mismatch_with_artifact_links_goes_manual(env):
    # 复核 P2:恢复成员数量须与产物来源链接事实一致——产物含 2 条来源
    # 链接而 claim 成员只命中 1 条(另一链接无对应成员)=无法唯一确认
    # 成员清单,转人工,不得以部分命中回填
    conn, config, ctx, work, state = env
    _seed_claim(conn, "in1", url="https://e.com/a")
    md = ("---\ndate: '2026-10-06'\ngenerated: true\nai_model: m\n"
          "entry_count: 2\ncost_cny: 0.01\ncost_pending: false\n---\n"
          "\n## 值得一瞥\n\n- [t](https://e.com/a)(s · 展示分 71)——p\n"
          "- [g](https://e.com/ghost)(s · 展示分 70)——q\n")  # ghost 无成员
    _commit_file(work, "2026-10-06", content=md)
    _run(["push", "origin", "main"], work)
    with pytest.raises(ManualIntervention, match="证据不足"):
        recover_issue(conn, "2026-10-06", ctx)
    # 未以部分命中落库:转人工先于 INSERT,无 digest_issue 行
    assert conn.execute("SELECT COUNT(*) FROM digest_issue WHERE"
                        " issue_date='2026-10-06'").fetchone()[0] == 0


def test_correct_refuses_when_ledger_diverges_from_remote(env):
    # 交界 B-缝C:restore 回退 ops_json/撤回事实后,库说 published 但远端
    # 尖端已无该路径(撤回已 push)——correct 不得基于回退认知重建文件
    # (已撤回内容以纠错名义重新上线);线上自洽校验转人工
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    _withdraw_confirmed(conn, ctx, work, state)
    with conn:                                   # 模拟 restore 回退到备份时点
        conn.execute(
            "UPDATE digest_issue SET ops_json=NULL, withdrawn_utc=NULL,"
            " withdraw_commit=NULL WHERE issue_date='2026-10-06'")
        conn.execute("DELETE FROM issue_freeze WHERE issue_date="
                     "'2026-10-06'")
    fixed = ("---\ndate: '2026-10-06'\ngenerated: true\nai_model: m\n"
             "entry_count: 1\ncost_cny: 0.01\ncost_pending: false\n---\n"
             "\n## 值得一瞥\n\n- [x](https://e.com)(s · 展示分 71)——p\n")
    with pytest.raises(ManualIntervention, match="线上|自洽|核对"):
        correct(conn, "2026-10-06", ctx, new_content=fixed)
    tip = _run(["rev-parse", "origin/main"], work)
    assert _run(["ls-tree", tip, f"{DIGEST_DIR}/2026-10-06.md"], work) == ""


def test_withdraw_not_confirmed_when_release_sha_unresolvable(env):
    # 交界 B-缝D:部署 SHA 本地不可解析 ≠ "路径已消失"——撤回确认须部署
    # 证据可验证;不可解析=证据不足保持 pending,不落 withdrawn 终态
    conn, config, ctx, work, state = env
    _publish_ok(conn, ctx, work)
    ctx.fetch_release_sha = lambda: "deadbeef" * 5    # 对象库不可达 SHA
    state["url_ok"] = False
    res = withdraw(conn, "2026-10-06", ctx, reason="内容有误")
    assert res.status == "pending"
    row = conn.execute("SELECT withdrawn_utc FROM digest_issue WHERE"
                       " issue_date='2026-10-06'").fetchone()
    assert row[0] is None


def test_ff_merge_overlapping_staged_goes_manual(env, tmp_path):
    # 交界 B-边缘:暂存遗留与远端更新重叠→ff merge 拒绝→转人工,而非
    # RuntimeError 逃逸 run_once 异常协议(无 fail 行/无 E8 通知)
    conn, config, ctx, work, state = env
    _make_draft(conn, work)
    _seed_claim(conn, "in1")
    (work / "README.md").write_text("local staged change", encoding="utf-8")
    _run(["add", "README.md"], work)                 # 暂存遗留
    other = tmp_path / "other"
    _run(["clone", ctx.remote_url, str(other)], tmp_path)
    _run(["config", "user.email", "t@t"], other)
    _run(["config", "user.name", "t"], other)
    (other / "README.md").write_text("remote moved on", encoding="utf-8")
    _run(["add", "."], other)
    _run(["commit", "-m", "elsewhere", "-q"], other)
    _run(["push", "origin", "main"], other)          # 同文件远端前进→重叠

    with pytest.raises(ManualIntervention, match="同步|sync|工作副本"):
        publish_issue(conn, "2026-10-06", ctx, final_keys=["in1"])
