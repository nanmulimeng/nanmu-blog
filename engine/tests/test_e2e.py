"""替身端到端集成(Task 24):小样本(≤5 条)全链贯通(collect→冻结→
预筛→评分→摘要→组装→发布→published)+三失败路径(E2 上游拒/E6 全挂
→failed+退出非零+首期抑制二期通知;单条失败剔除不挂整期)+重启重放
四窗口(①有效响应复用零新增;②缺失按授权补发;③unknown 预占保留,
等待条件与名额内跨轮重发;④发布恢复零模型调用)。LLM 一律
httpx.MockTransport 替身,远端=本地 bare repo,零真实网络。"""

import json
from datetime import datetime, timedelta, timezone

import httpx

from nanmu_engine.score import score_entry

from test_collect import _add_item
from test_publish import _run
from test_run import (NOW, _attempts_for, _draft_row, _entry, _freeze,
                      _run_once, _transport, env)

FETCHED = datetime(2026, 10, 6, 7, 0, tzinfo=timezone.utc)


def _add(env, url, title, content):
    _add_item(env["up_conn"], env["up_sid"], url, title,
              fetched=FETCHED, content=content)


class _Counting(httpx.BaseTransport):
    """包装替身并按 user 内容分流计数(验证某成员零新增/按次补发)。"""

    def __init__(self, inner, marker):
        self._inner, self._marker = inner, marker
        self.counts = {"marker": 0, "other": 0}

    def handle_request(self, request):
        try:
            user = json.loads(request.content.decode("utf-8")
                              )["messages"][1]["content"]
        except Exception:
            user = ""
        self.counts["marker" if self._marker in user else "other"] += 1
        return self._inner.handle_request(request)


def _net_down():
    def handler(request):
        raise httpx.ConnectError("net down", request=request)
    return httpx.MockTransport(handler)


def _fail_all():
    # 400=E1.request no_retry(P1-6 后可重试失败保存进度不落 E6,
    # E6 通知语义用不可重试失败覆盖)
    def handler(request):
        return httpx.Response(400, json={"error": "bad request"})
    return httpx.MockTransport(handler)


def _remote_files(env):
    return _run(["ls-tree", "--name-only", "-r", "origin/main"], env["work"])


def _status(env, issue_date):
    row = env["conn"].execute(
        "SELECT status FROM digest_issue WHERE issue_date=?",
        (issue_date,)).fetchone()
    return row[0] if row else None


# ---------- 全链贯通(验收:collect→…→published,零通知) ----------

def test_full_chain_collect_to_published(env):
    conn = env["conn"]
    for i in (1, 2, 3):
        _add(env, f"https://e.com/f{i}", f"全链条目{i}", f"全链正文{i}。")

    code = _run_once(env, transport=_transport(env["config"]))

    assert code == 0
    assert _status(env, "2026-10-06") == "published"
    # 远端(本地 bare repo)树内已含产物文件
    assert "digest/2026-10-06.md" in _remote_files(env)
    # 占用协议落定:入选 used;全部评分子务结清(actual 入账)
    used = conn.execute("SELECT COUNT(*) FROM entry WHERE"
                        " status='used'").fetchone()[0]
    assert used >= 1
    assert _attempts_for(conn, "2026-10-06") == 3 * 2 + used  # 评分+摘要
    assert conn.execute(
        "SELECT COUNT(*) FROM receipt_attempt WHERE issue_date=?"
        " AND actual_micro_cny IS NULL", ("2026-10-06",)).fetchone()[0] == 0
    assert env["sent"] == []                       # 成功期零通知


# ---------- 失败路径:E2 上游拒(首期抑制,二期通知) ----------

def test_e2_first_period_suppressed_second_notifies(env):
    bad = str(env["tmp_path"] / "no-such-upstream.json")

    code = _run_once(env, today="2026-10-06", upstream=bad,
                     transport=_transport(env["config"]))
    assert code == 3
    assert env["conn"].execute(
        "SELECT status, fail_reason FROM digest_issue WHERE"
        " issue_date='2026-10-06'").fetchone() == ("failed", "E2.upstream")
    assert env["sent"] == []                       # 首期:不发送不落表

    _add(env, "https://e.com/e2b", "二期条目", "二期正文。")
    code2 = _run_once(env, today="2026-10-07", upstream=bad,
                      transport=_transport(env["config"]))
    assert code2 == 3
    assert _status(env, "2026-10-07") == "failed"
    assert [k for k, _ in env["sent"]] == ["E2.upstream:2026-10-07"]


# ---------- 失败路径:E6 全挂(首期抑制,二期通知) ----------

def test_e6_all_failed_first_suppressed_second_notifies(env):
    _add(env, "https://e.com/e6a", "全挂A", "全挂正文A。")
    code = _run_once(env, today="2026-10-06", transport=_fail_all())
    assert code == 3
    assert env["conn"].execute(
        "SELECT status, fail_reason FROM digest_issue WHERE"
        " issue_date='2026-10-06'").fetchone() == ("failed", "E6.all_failed")
    assert env["sent"] == []                       # 首期:不发送不落表

    _add(env, "https://e.com/e6b", "全挂B", "全挂正文B。")
    code2 = _run_once(env, today="2026-10-07", transport=_fail_all())
    assert code2 == 3
    assert [k for k, _ in env["sent"]] == ["E6.all_failed:2026-10-07"]


# ---------- 失败路径:单条评分失败剔除,不挂整期 ----------

def test_single_entry_failure_excluded_issue_publishes(env):
    conn = env["conn"]
    _add(env, "https://e.com/bad", "坏条目", "带失败标记XYZ的正文。")
    _add(env, "https://e.com/good", "好条目", "正常正文。")

    code = _run_once(env, transport=_transport(
        env["config"], score_fail_marker="失败标记XYZ"))

    assert code == 0
    assert _status(env, "2026-10-06") == "published"
    # 坏条目无 analysis(双侧各败一次后剔除);好条目走完全链
    assert conn.execute(
        "SELECT COUNT(*) FROM analysis a JOIN entry e ON e.id=a.entry_id"
        " WHERE e.identity_key='entry:https://e.com/bad'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM analysis").fetchone()[0] == 1
    assert _attempts_for(conn, "2026-10-06") == 2 + 2 + 1  # 坏2+好2+好摘要


# ---------- 重放窗口①②:有效响应复用零新增,缺失按授权补发 ----------

def test_replay_valid_response_reused_missing_rescored(env):
    conn = env["conn"]
    a = _entry(conn, "k-reuse-a", title="复用A", body="复用正文A。")
    b = _entry(conn, "k-reuse-b", title="补发B", body="补发正文B。")
    _freeze(conn, "2026-10-06", [a, b], frozen="2026-10-06T08:31:00Z")
    # kill 点①:A 的评分响应已有效(received+过 E4)落库
    out = score_entry(conn, env["config"], a, issue_date="2026-10-06",
                      transport=_transport(env["config"]), now=NOW)
    assert out.status == "completed"

    counting = _Counting(_transport(env["config"]), "复用A")
    code = _run_once(env, transport=counting)

    assert code == 0
    assert _status(env, "2026-10-06") == "published"
    # ① A 复用:直调产生的两笔回执零新增 attempt(评分零网络;
    #    marker 计到的 1 次是 A 首次 understand,属正常新增)
    ph = ",".join("?" * len(out.receipt_ids))
    assert conn.execute(
        f"SELECT COUNT(*) FROM receipt_attempt WHERE receipt_id IN ({ph})",
        out.receipt_ids).fetchone()[0] == len(out.receipt_ids)
    assert counting.counts["marker"] == 1
    assert counting.counts["other"] >= 2           # ② B 缺失:按授权补发


# ---------- 重放窗口③:unknown 预占保留,等待条件内零重发 ----------

def test_replay_unknown_waits_then_resends_after_window(env):
    conn = env["conn"]
    c = _entry(conn, "k-unknown", title="等待C", body="等待正文C。")
    _freeze(conn, "2026-10-06", [c], frozen="2026-10-06T08:31:00Z")
    # attempt.started_utc 落真实墙钟(注入 now 只影响授权判定),等待窗
    # 断言须以真实钟为基准:t0-1min 产生 unknown,t0 处于窗内,t0+31 过窗
    t0 = datetime.now(timezone.utc)
    # kill 点③:双侧评分为传输 unknown(预占在,无 analysis)
    out = score_entry(conn, env["config"], c, issue_date="2026-10-06",
                      transport=_net_down(), now=t0 - timedelta(minutes=1))
    assert out.status == "unknown"
    assert _attempts_for(conn, "2026-10-06") == 2

    counting = _Counting(_transport(env["config"]), "等待C")
    # 窗内(<30min)重跑:不重发、期不落 failed,保存状态续接
    code = _run_once(env, transport=counting, now=t0)
    assert code == 4
    assert _status(env, "2026-10-06") is None      # 无 digest_issue 行
    assert _attempts_for(conn, "2026-10-06") == 2  # 零新增
    assert counting.counts["marker"] == 0

    # 窗口过后(>30min)重跑:unknown_retry 通道按授权补发,直至发布
    code2 = _run_once(env, transport=counting,
                      now=t0 + timedelta(minutes=31))
    assert code2 == 0
    assert _status(env, "2026-10-06") == "published"
    assert counting.counts["marker"] >= 2          # 双侧补发(+摘要)
    assert _attempts_for(conn, "2026-10-06") == 2 + 2 + 1


# ---------- 重放窗口④:发布恢复(draft→push→确认)零模型调用 ----------

def test_replay_draft_publish_recovery_zero_llm_calls(env):
    conn = env["conn"]
    c = _entry(conn, "k-draft4", status="selected", claim="2026-10-04")
    _draft_row(conn, env["work"], "2026-10-04", [c["entry_id"]],
               status="draft", frozen="2026-10-03T08:31:00Z")

    def boom(request):
        raise AssertionError("发布恢复不得发起模型调用")

    code = _run_once(env, today="2026-10-04",
                     transport=httpx.MockTransport(boom))

    assert code == 0
    assert _status(env, "2026-10-04") == "published"
    assert "digest/2026-10-04.md" in _remote_files(env)
    assert _attempts_for(conn, "2026-10-04") == 0  # 零模型调用
    assert conn.execute("SELECT status FROM entry WHERE"
                        " identity_key='k-draft4'").fetchone()[0] == "used"


# ---------- 修复轮 C1:上期已发布成员不得借旧 analysis 重复入选 ----------

def test_published_member_not_reselected_next_issue(env):
    """上期 published(used)的成员次日仍在采集窗内:预筛按 used 排除,
    入选查询不得绕过预筛四去向把旧 analysis 行重新入选(重复发布 +
    used 状态翻转,违反 spec §5.2 与占用协议)。"""
    conn = env["conn"]
    _add(env, "https://e.com/dup", "重复条目", "重复正文。")
    assert _run_once(env, today="2026-10-05",
                     transport=_transport(env["config"])) == 0
    assert conn.execute("SELECT status FROM entry WHERE"
                        " identity_key='url:https://e.com/dup'"
                        ).fetchone()[0] == "used"

    # 次日:上游重抓同条(仍在窗,fetched 刷新)+一条新条目
    with env["up_conn"]:
        env["up_conn"].execute(
            "UPDATE item SET fetched_utc=? WHERE url=?",
            ("2026-10-06T07:30:00Z", "https://e.com/dup"))
    _add(env, "https://e.com/fresh", "新条目", "新正文。")
    code = _run_once(env, today="2026-10-06",
                     transport=_transport(env["config"]))

    assert code == 0
    assert _status(env, "2026-10-06") == "published"
    # 旧成员:状态保持 used(不被改写),产物不含其链接
    assert conn.execute("SELECT status FROM entry WHERE"
                        " identity_key='url:https://e.com/dup'"
                        ).fetchone()[0] == "used"
    from test_publish import DIGEST_DIR
    day2 = (env["work"] / DIGEST_DIR / "2026-10-06.md").read_text(
        encoding="utf-8")
    assert "https://e.com/dup" not in day2


# ---------- 交界核验 B-缝B:清算口径=最终产物成员(与恢复路径一致) ----------

def test_safety_excluded_member_settles_rejected_on_publish(env):
    """发布主链清算口径=最终产物成员(assemble ready),与恢复路径
    entry_ids 口径一致——被安全剔除(url scheme 非白名单)的入选成员置
    rejected,不因走发布主链被置 used(丧失再入选资格)。注:采集侧
    normalize R0 白名单本就挡住 javascript url 入库(正常链路不可达),
    本测试直插 entry 构造,锁的是清算口径的防御性统一。"""
    conn = env["conn"]
    bad = _entry(conn, "k-badurl", title="坏URL条目", body="正常正文足够长度以入选。",
                 url="javascript:alert(1)")
    good = _entry(conn, "k-good2", title="好条目", body="正常正文。")
    _freeze(conn, "2026-10-06", [bad, good], frozen="2026-10-06T08:31:00Z")

    code = _run_once(env, transport=_transport(env["config"]))

    assert code == 0
    assert _status(env, "2026-10-06") == "published"
    assert conn.execute("SELECT status FROM entry WHERE"
                        " identity_key='k-badurl'"
                        ).fetchone()[0] == "rejected"   # 不进产物=不 used
    assert conn.execute("SELECT status FROM entry WHERE"
                        " identity_key='k-good2'"
                        ).fetchone()[0] == "used"
