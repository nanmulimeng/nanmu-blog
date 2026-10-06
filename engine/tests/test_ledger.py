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
