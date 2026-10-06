"""ledger 授权闸门测试(种子=model-calls §3 规则 1 + 验收 6 + budget.md 预占公式)。"""

import itertools
from pathlib import Path

import pytest

from nanmu_engine.config import load_config
from nanmu_engine.db import connect_db, migrate
from nanmu_engine.ledger import authorize, sync_budget_limits

ENGINE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def env(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    config = load_config(ENGINE_ROOT)
    sync_budget_limits(conn, config)
    return conn, config


def _authorize(conn, config, **overrides):
    kwargs = dict(
        purpose="score", model="deepseek-flash", request_hash="h" * 64,
        identity_key="url:https://example.com/a", token_count=1000,
        issue_date="2026-10-06", origin="initial",
    )
    kwargs.update(overrides)
    return authorize(conn, config, **kwargs)


def _set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO engine_meta (key, value, updated_utc)"
        " VALUES (?, ?, datetime('now'))"
        " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value))
    conn.commit()


_seed_seq = itertools.count()


def _seed_attempt(conn, *, minutes_ago=0.0, reserved=0, actual=None,
                  issue_date="2026-10-06", status="pending"):
    """预填一条 attempt 行(窗口/金额聚合测试用)。"""
    import datetime as dt
    started = (dt.datetime.now(dt.timezone.utc)
               - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute(
        "INSERT INTO receipt (logical_key, provider, endpoint, request_hash,"
        " service, purpose, model, status, created_utc)"
        " VALUES (?, 'deepseek', '/chat/completions', 'rh', 'llm', 'score',"
        " 'deepseek-flash', 'pending', ?)",
        (f"seed-{next(_seed_seq)}", started))
    conn.execute(
        "INSERT INTO receipt_attempt (receipt_id, attempt_no, issue_date,"
        " started_utc, status, attempt_origin, reserved_micro_cny, actual_micro_cny,"
        " pricing_version) VALUES (?, 1, ?, ?, ?, 'initial', ?, ?, 'deepseek-2026-10-02')",
        (cur.lastrowid, issue_date, started, status, reserved, actual))
    conn.commit()


# ---------- pay_paused 闸门(种子 1) ----------

def test_pay_paused_gate(env):
    conn, config = env
    _set_meta(conn, "pay_paused", "1")
    result = _authorize(conn, config)
    assert result.status == "rejected" and result.reject_reason == "pay_paused"

    conn.execute("DELETE FROM engine_meta WHERE key='pay_paused'")
    conn.commit()
    result = _authorize(conn, config)   # 键缺失=裸恢复异常态,同拒
    assert result.status == "rejected" and result.reject_reason == "key_missing"

    _set_meta(conn, "pay_paused", "0")
    result = _authorize(conn, config)
    assert result.status == "reserved"


# ---------- 窗口(种子 2) ----------

def test_hour_window_full_rejects_without_writing_attempt(env):
    conn, config = env
    for _ in range(100):  # per_hour=100(真配置)
        _seed_attempt(conn, minutes_ago=10)
    before = conn.execute("SELECT COUNT(*) FROM receipt_attempt").fetchone()[0]
    result = _authorize(conn, config)
    assert result.status == "rejected" and result.reject_reason == "window"
    after = conn.execute("SELECT COUNT(*) FROM receipt_attempt").fetchone()[0]
    assert after == before  # 拒且不写预占行


def test_day_window_counts_recent_only(env):
    conn, config = env
    # 小时窗口未满(50),但天窗口满:近 24h 400 条(per_day=400)
    for i in range(400):
        _seed_attempt(conn, minutes_ago=60 + (i % 100) / 100)
    result = _authorize(conn, config)
    assert result.status == "rejected" and result.reject_reason == "window"


# ---------- 金额 ----------

def test_monthly_money_cap_rejects(env):
    conn, config = env
    # 已结算 49_999_000 + 预占 1_000 ≥ monthly 50_000_000
    _seed_attempt(conn, minutes_ago=5, reserved=1_000, actual=49_999_000)
    result = _authorize(conn, config)
    assert result.status == "rejected" and result.reject_reason == "money"


def test_pending_reservation_counts_as_money(env):
    conn, config = env
    # 未决预占同样计入:pending 50_000_000(无 actual)
    _seed_attempt(conn, minutes_ago=5, reserved=50_000_000, actual=None)
    result = _authorize(conn, config)
    assert result.status == "rejected" and result.reject_reason == "money"


def test_per_issue_cap_rejects(env):
    conn, config = env
    # 当期已耗 1_000_000 = per_issue 上限;月度余量充足
    _seed_attempt(conn, minutes_ago=5, reserved=1_000_000, actual=1_000_000)
    result = _authorize(conn, config)
    assert result.status == "rejected" and result.reject_reason == "money"


# ---------- 计数不可得 ----------

def test_token_count_unavailable_rejects(env):
    conn, config = env
    result = _authorize(conn, config, token_count=None)
    assert result.status == "rejected"
    assert result.reject_reason == "token_count_unavailable"


# ---------- budget 表行缺失 ----------

def test_budget_row_missing_rejects(env):
    conn, config = env
    conn.execute("DELETE FROM budget WHERE service='llm'")
    conn.commit()
    result = _authorize(conn, config)
    assert result.status == "rejected" and result.reject_reason == "key_missing"


# ---------- 预占写入与公式 ----------

def test_reserved_formula_includes_output_cap(env):
    conn, config = env
    # token_count=1_000_000,input ¥2/M=2_000_000 微元/M,out ¥8/M,
    # max_output_tokens=200 → 1M×2 + 200×8 = 2_001_600 微元(输出上限必含)
    result = _authorize(conn, config, token_count=1_000_000)
    assert result.status == "reserved"
    assert result.reserved_micro_cny == 2_001_600


def test_reserved_ceil_to_integer_micro(env):
    import dataclasses
    from nanmu_engine.config import PricingRow
    conn, config = env
    # 用非 1M 整倍数输入价构造小数:40_001 微元/M × 1 token = 0.04 微元
    # (200×8_000_000=1_600_000_000 → 1600;合计 1600.04 → ceil 1601)
    odd = dataclasses.replace(
        config.budget,
        pricing=(PricingRow("test", "deepseek-flash", 40_001, 40, 8_000_000),))
    odd_config = dataclasses.replace(config, budget=odd)
    result = _authorize(conn, odd_config, token_count=1)
    assert result.reserved_micro_cny == 1601


def test_first_attempt_creates_receipt_and_row(env):
    conn, config = env
    result = _authorize(conn, config)
    assert result.status == "reserved"
    assert result.attempt_no == 1
    row = conn.execute(
        "SELECT status, attempt_origin, issue_date, reserved_micro_cny"
        " FROM receipt_attempt WHERE id=?", (result.attempt_id,)).fetchone()
    assert row[0] == "pending" and row[1] == "initial"
    assert row[2] == "2026-10-06"
    receipt = conn.execute(
        "SELECT logical_key, status FROM receipt WHERE id=?",
        (result.receipt_id,)).fetchone()
    assert receipt[1] == "pending"
    assert "score" in receipt[0] and config.budget.default_model in receipt[0]


def test_retry_attempt_reuses_receipt(env):
    conn, config = env
    first = _authorize(conn, config)
    second = _authorize(conn, config, origin="retry",
                        request_hash="h" * 64)  # 同 logical_key
    assert second.receipt_id == first.receipt_id
    assert second.attempt_no == 2
    n = conn.execute("SELECT COUNT(*) FROM receipt").fetchone()[0]
    assert n == 1  # 不建新 receipt


def test_sync_budget_limits_writes_rows(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    config = load_config(ENGINE_ROOT)
    sync_budget_limits(conn, config)
    row = conn.execute(
        "SELECT per_minute, per_hour, per_day FROM budget WHERE service='llm'"
    ).fetchone()
    assert row == (10, 100, 400)
    conn.close()


# ---------- Task 6:record_failure + can_retry(验收 7/7b/7c/7d) ----------

import datetime as dt

from nanmu_engine.ledger import can_retry, record_failure


def _run_attempt(conn, config, *, origin="initial", error_class="retryable",
                 fail_detail=None, request_hash="h" * 64, usage=None):
    """授权→失败落库,返回 (result, attempt 行)。"""
    result = _authorize(conn, config, origin=origin,
                        request_hash=request_hash)
    assert result.status == "reserved", result
    record_failure(conn, config, result, error_class,
                   fail_detail or {"http_status": None, "matrix_code": "x",
                                   "message": "m"}, usage=usage)
    row = conn.execute(
        "SELECT attempt_no, status, attempt_origin, error_class"
        " FROM receipt_attempt WHERE id=?", (result.attempt_id,)).fetchone()
    return result, row


def _started_of(conn, attempt_id):
    return conn.execute(
        "SELECT started_utc FROM receipt_attempt WHERE id=?",
        (attempt_id,)).fetchone()[0]


def test_7d_replay_from_disk_after_close(env, tmp_path):
    conn, config = env
    result, row = _run_attempt(conn, config, error_class="no_retry")  # HTTP 400
    assert row[1] == "failed"
    conn.close()

    conn2 = connect_db(str(tmp_path / "engine.db"))  # 仅凭落库行数据重放
    verdict = can_retry(conn2, config, "deepseek/chat/completions/score/deepseek-flash/" + "h" * 64,
                        now_utc=dt.datetime.now(dt.timezone.utc))
    assert verdict.allowed is False and verdict.reason == "error_class_no_retry"
    conn2.close()


def test_7d_503_counts_against_normal_quota(env):
    conn, config = env
    _run_attempt(conn, config, error_class="retryable")            # initial
    _run_attempt(conn, config, origin="retry", error_class="retryable")  # retry
    key = "deepseek/chat/completions/score/deepseek-flash/" + "h" * 64
    verdict = can_retry(conn, config, key, dt.datetime.now(dt.timezone.utc))
    assert verdict.allowed is False
    assert verdict.reason == "normal_quota_exhausted"


def test_7d_normal_exhausted_unknown_unused_still_rejects(env):
    conn, config = env
    # 普通耗尽 + unknown_retry_used=0 → 仍拒(两类不互借)
    _run_attempt(conn, config, error_class="retryable")
    _run_attempt(conn, config, origin="retry", error_class="retryable")
    key = "deepseek/chat/completions/score/deepseek-flash/" + "h" * 64
    used = conn.execute("SELECT unknown_retry_used FROM receipt").fetchone()[0]
    assert used == 0
    verdict = can_retry(conn, config, key, dt.datetime.now(dt.timezone.utc))
    assert verdict.allowed is False
    assert verdict.reason == "normal_quota_exhausted"


def test_7d_origin_immutable_unknown_channel_returns_503(env):
    conn, config = env
    # 序列:attempt1 initial/超时未知 → ≥30min 后 unknown 通道 attempt2 返回 503
    r1, row1 = _run_attempt(conn, config, error_class="unknown")
    assert row1[1] == "unknown"
    key = "deepseek/chat/completions/score/deepseek-flash/" + "h" * 64

    started1 = dt.datetime.fromisoformat(_started_of(conn, r1.attempt_id))
    not_due = can_retry(conn, config, key, started1 + dt.timedelta(minutes=10))
    assert not_due.allowed is False and not_due.reason == "unknown_wait"
    due = can_retry(conn, config, key, started1 + dt.timedelta(minutes=31))
    assert due.allowed is True and due.channel == "unknown_retry"

    # unknown 通道授权:同事务置 unknown_retry_used=1
    r2, row2 = _run_attempt(conn, config, origin="unknown_retry",
                            error_class="retryable")  # 返回 503
    assert row2[2] == "unknown_retry"           # origin 保持,不因返回类型改写
    assert row2[3] == "retryable"
    used = conn.execute("SELECT unknown_retry_used FROM receipt").fetchone()[0]
    assert used == 1

    # 普通名额仍有剩余(attempt1 initial 占 1;unknown_retry 不占)→ attempt3 走普通
    verdict = can_retry(conn, config, key, dt.datetime.now(dt.timezone.utc))
    assert verdict.allowed is True and verdict.channel == "normal"
    r3, row3 = _run_attempt(conn, config, origin="retry",
                            error_class="retryable")
    assert row3[2] == "retry"
    normal_used = conn.execute(
        "SELECT COUNT(*) FROM receipt_attempt"
        " WHERE attempt_origin IN ('initial','retry')").fetchone()[0]
    assert normal_used == 2  # attempt3 计入普通尝试已用数
    # 总行数 3 = max_attempts+1 → 硬上限拒
    final = can_retry(conn, config, key, dt.datetime.now(dt.timezone.utc))
    assert final.allowed is False and final.reason == "hard_cap"


def test_6_quota_counts_attempts_not_error_classes(env):
    conn, config = env
    key = "deepseek/chat/completions/score/deepseek-flash/" + "h" * 64
    # A:initial+unknown → 30min 窗口内等待 unknown 通道,不立即普通重发;
    #    失败更新不改写 attempt_origin(initial 保持)
    r1, row1 = _run_attempt(conn, config, error_class="unknown")
    assert row1[2] == "initial"
    verdict = can_retry(conn, config, key, dt.datetime.now(dt.timezone.utc))
    assert verdict.allowed is False and verdict.reason == "unknown_wait"

    # B:独立 key,initial+retryable → 立即经普通通道(已用 1 < max_attempts=2)
    key_b = "deepseek/chat/completions/score/deepseek-flash/" + "g" * 64
    _run_attempt(conn, config, error_class="retryable",
                 request_hash="g" * 64)
    verdict_b = can_retry(conn, config, key_b, dt.datetime.now(dt.timezone.utc))
    assert verdict_b.allowed is True and verdict_b.channel == "normal"
    # 普通已用数=origin 计数(不按 error_class):B 场景再发后 2=max_attempts → 拒
    _run_attempt(conn, config, origin="retry", error_class="retryable",
                 request_hash="g" * 64)
    verdict_b2 = can_retry(conn, config, key_b, dt.datetime.now(dt.timezone.utc))
    assert verdict_b2.allowed is False
    assert verdict_b2.reason == "normal_quota_exhausted"


def test_7c_max2_two_normal_failures_no_send_after_restart(env, tmp_path):
    conn, config = env
    _run_attempt(conn, config, error_class="retryable")
    _run_attempt(conn, config, origin="retry", error_class="retryable")
    conn.close()

    conn2 = connect_db(str(tmp_path / "engine.db"))
    key = "deepseek/chat/completions/score/deepseek-flash/" + "h" * 64
    verdict = can_retry(conn2, config, key, dt.datetime.now(dt.timezone.utc))
    # 普通已用 2=max_attempts,总数 2<3 不构成许可(重启不重置)
    assert verdict.allowed is False
    assert verdict.reason == "normal_quota_exhausted"
    conn2.close()


def test_record_failure_settles_usage(env):
    conn, config = env
    result = _authorize(conn, config)
    usage = {"prompt_tokens": 1_000_000, "prompt_cache_hit_tokens": 0,
             "prompt_cache_miss_tokens": 1_000_000, "completion_tokens": 50}
    record_failure(conn, config, result, "no_retry",
                   {"http_status": 400, "matrix_code": "E1.request",
                    "message": "bad"}, usage=usage)
    row = conn.execute(
        "SELECT status, error_class, actual_micro_cny, usage_json"
        " FROM receipt_attempt WHERE id=?", (result.attempt_id,)).fetchone()
    assert row[0] == "failed" and row[1] == "no_retry"
    # 1M×2 + 50×8 = 2_000_400 微元(有 usage 先结算)
    assert row[2] == 2_000_400
    import json as _json
    assert _json.loads(row[3])["prompt_tokens"] == 1_000_000
