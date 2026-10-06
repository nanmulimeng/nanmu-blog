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
    publish_issue,
    recover_issue,
    update_op_stage,
    visible_status,
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
                entry_id=None):
    cur = conn.execute(
        "INSERT INTO entry (identity_key, url, title, source_name,"
        " source_tier, discovered_utc, content_text, status, claim_issue)"
        " VALUES (?, 'https://e.com', 't', 'src', 'T1',"
        " '2026-10-06T00:00:00Z', 'b', ?, ?)",
        (key, status, claim))
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
    sha = _commit_file(work, "2026-10-06")         # commit 成功、DB 未记 draft
    out = recover_issue(conn, "2026-10-06", ctx)
    assert out.status == "draft"
    row = conn.execute(
        "SELECT status, git_commit, content_sha256 FROM digest_issue"
        " WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == "draft" and row[1] == sha     # 复用提交不重组
    blob = _run(["show", f"{sha}:{DIGEST_DIR}/2026-10-06.md"], work,
                binary=True)
    assert row[2] == hashlib.sha256(blob).hexdigest()
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
