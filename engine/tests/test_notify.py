"""通知去重测试(种子=scheduling-ops 验收 6;§3 规则 7)。
同 key UPSERT:首现 INSERT、重试成功 UPDATE 原行(dedup_key 主键,同 key
二次 INSERT 必冲突,不得另起一行);发送替身计数;崩溃承诺收窄=正常
持久化后同 key 零重发,不设次数上限断言。"""

import sqlite3

import pytest

from nanmu_engine.db import connect_db, migrate
from nanmu_engine.notify import notify, notify_event, notify_monthly


@pytest.fixture
def conn(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    return conn


def _fails_first(n_fail=1):
    """发送替身:前 n_fail 次抛异常,之后成功。"""
    state = {"calls": 0}

    def send(dedup_key, message):
        state["calls"] += 1
        if state["calls"] <= n_fail:
            raise ConnectionError("channel down")
        return "sent"
    return send, state


def _counter():
    state = {"calls": 0}

    def send(dedup_key, message):
        state["calls"] += 1
        return "sent"
    return send, state


def _rows(conn):
    return conn.execute(
        "SELECT dedup_key, result FROM notify_sent ORDER BY dedup_key"
    ).fetchall()


# ---------- 验收 6:同 key UPSERT 与零重发 ----------

def test_same_key_after_persist_never_resends(conn):
    send, state = _counter()
    assert notify(conn, "E6.all_failed:2026-10-05", "m1", send=send) == "sent"
    assert notify(conn, "E6.all_failed:2026-10-05", "m2", send=send) == \
        "deduped"                      # 正常持久化后同 key 零重发
    assert state["calls"] == 1
    assert _rows(conn) == [("E6.all_failed:2026-10-05", "sent")]


def test_same_key_retry_success_updates_original_row(conn):
    # 首现发送失败(有界重试全败)→落 failed 行;重试成功→UPDATE 原行,
    # 无第二次 INSERT、无主键冲突、不另起一行
    send, state = _fails_first(n_fail=3)
    assert notify(conn, "E9:2026-10-06", "m", send=send,
                  retries=1) == "failed"
    assert _rows(conn) == [("E9:2026-10-06", "failed")]
    ok, state2 = _counter()
    assert notify(conn, "E9:2026-10-06", "m", send=ok) == "sent"
    assert _rows(conn) == [("E9:2026-10-06", "sent")]   # 仍一行
    assert conn.execute("SELECT COUNT(*) FROM notify_sent").fetchone()[0] == 1
    assert state["calls"] == 1 and state2["calls"] == 1
    sent_utc = conn.execute("SELECT sent_utc FROM notify_sent"
                            ).fetchone()[0]
    assert sent_utc                                   # UPDATE 刷新 sent_utc


def test_send_failure_bounded_retry_does_not_double_send(conn):
    # 有界重试:retries=3 → 同一次 notify 内最多 3 次发送尝试
    send, state = _fails_first(n_fail=10)
    result = notify(conn, "E1.config:2026-10-06", "m", send=send, retries=3)
    assert result == "failed"
    assert state["calls"] == 3                         # 有界,不无限


# ---------- 事件类入口:立即类/连续 2 期类/月度 ----------

def test_immediate_class_sends_at_once_and_dedups_within_period(conn):
    send, state = _counter()
    for _ in range(2):                                 # 同期重跑不重发
        notify_event(conn, "E8", "2026-10-06", "push 冲突", send=send)
    assert state["calls"] == 1
    assert _rows(conn) == [("E8:2026-10-06", "sent")]


def test_two_period_class_first_suppressed_second_sent(conn):
    send, state = _counter()
    # 首期失败(无前科)→判二期前不发送
    assert notify_event(conn, "E6.all_failed", "2026-10-05", "全挂",
                        send=send) == "suppressed_first"
    assert state["calls"] == 0
    assert _rows(conn) == []                           # 未发送不落表
    # 他期已有同子类失败(digest_issue failed 行)→本期发送
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, status,"
            " created_utc, fail_reason) VALUES ('2026-10-05','[]','failed',"
            " '2026-10-05T09:00:00Z', 'E6.all_failed')")
    assert notify_event(conn, "E6.all_failed", "2026-10-06", "又全挂",
                        send=send) == "sent"
    assert state["calls"] == 1
    assert _rows(conn) == [("E6.all_failed:2026-10-06", "sent")]


def test_two_period_same_period_second_fail_one_letter(conn):
    # 同子类同期二次失败→一封(去重)
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, status,"
            " created_utc, fail_reason) VALUES ('2026-10-04','[]','failed',"
            " '2026-10-04T09:00:00Z', 'E2.upstream')")
    send, state = _counter()
    notify_event(conn, "E2.upstream", "2026-10-05", "上游失败", send=send)
    notify_event(conn, "E2.upstream", "2026-10-05", "上游又失败", send=send)
    assert state["calls"] == 1
    assert conn.execute("SELECT COUNT(*) FROM notify_sent").fetchone()[0] == 1


def test_cross_period_new_key(conn):
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, status,"
            " created_utc, fail_reason) VALUES ('2026-10-05','[]','failed',"
            " '2026-10-05T09:00:00Z', 'E6.all_failed')")
    send, state = _counter()
    notify_event(conn, "E6.all_failed", "2026-10-06", "m", send=send)
    notify_event(conn, "E6.all_failed", "2026-10-07", "m", send=send)
    # 跨期→新键→各发一封
    assert state["calls"] == 2
    assert [r[0] for r in _rows(conn)] == ["E6.all_failed:2026-10-06",
                                           "E6.all_failed:2026-10-07"]


def test_monthly_warning_one_per_month(conn):
    send, state = _counter()
    notify_monthly(conn, "2026-10", "¥40 预警", send=send)
    notify_monthly(conn, "2026-10", "¥40 预警", send=send)
    assert state["calls"] == 1
    assert _rows(conn) == [("warn-monthly:2026-10", "sent")]
    notify_monthly(conn, "2026-11", "¥40 预警", send=send)   # 跨月新键
    assert state["calls"] == 2
    assert [r[0] for r in _rows(conn)] == ["warn-monthly:2026-10",
                                           "warn-monthly:2026-11"]


def test_config_error_key_carries_hash_suffix(conn):
    # 配置错误类附配置 hash:变更后新键(变更前的键不再去重新事件)
    send, state = _counter()
    notify_event(conn, "E1.config", "2026-10-06", "bad",
                 send=send, key_extra="hash-a")
    notify_event(conn, "E1.config", "2026-10-06", "bad",
                 send=send, key_extra="hash-a")
    notify_event(conn, "E1.config", "2026-10-06", "bad",
                 send=send, key_extra="hash-b")
    assert state["calls"] == 2
    assert [r[0] for r in _rows(conn)] == [
        "E1.config:2026-10-06:hash-a", "E1.config:2026-10-06:hash-b"]
