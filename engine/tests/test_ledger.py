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


def _seed_attempt(conn, *, minutes_ago=0.0, started_utc=None, reserved=0,
                  actual=None, issue_date="2026-10-06", status="pending"):
    """预填一条 attempt 行(窗口/金额聚合测试用;started_utc=绝对时间)。"""
    import datetime as dt
    started = started_utc or (dt.datetime.now(dt.timezone.utc)
                              - dt.timedelta(minutes=minutes_ago)
                              ).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    import dataclasses
    # token_count=1_000_000,input ¥2/M=2_000_000 微元/M,out ¥8/M,
    # max_output_tokens=200 → 1M×2 + 200×8 = 2_001_600 微元(输出上限必含)
    # 期红线含本次预占(C2):默认 1M 上限容不下这笔,构造充足 odd 配置
    odd = dataclasses.replace(config.budget, per_issue_micro_cny=50_000_000)
    result = _authorize(conn, dataclasses.replace(config, budget=odd),
                        token_count=1_000_000)
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


# ---------- Task 7:record_response / reconcile / issue_cost_snapshot(验收 8/9/10) ----------

from nanmu_engine.ledger import issue_cost_snapshot, record_failure, record_response, reconcile


def _ok_result(prompt_tokens=100, completion_tokens=50) -> "LLMResult":
    from nanmu_engine.llm import LLMResult
    return LLMResult(
        http_status=200, finish_reason="stop",
        content='{"attentionScore": 60}', json_parsed=True,
        usage={"prompt_tokens": prompt_tokens,
               "prompt_cache_hit_tokens": 0,
               "prompt_cache_miss_tokens": prompt_tokens,
               "completion_tokens": completion_tokens},
        provider_request_id="resp-x", error_message=None)


def test_record_response_persists_received_and_settles(env):
    conn, config = env
    import dataclasses
    # C2 后预占不得越期红线:token_count=1M 需充足期上限才可授权
    odd = dataclasses.replace(config.budget, per_issue_micro_cny=50_000_000)
    odd_cfg = dataclasses.replace(config, budget=odd)
    ref = _authorize(conn, odd_cfg, token_count=1_000_000)
    record_response(conn, odd_cfg, ref, _ok_result(prompt_tokens=1_000_000))
    attempt = conn.execute(
        "SELECT status, actual_micro_cny, usage_json FROM receipt_attempt"
        " WHERE id=?", (ref.attempt_id,)).fetchone()
    assert attempt[0] == "received"
    # 1M×2 + 50×8 = 2_000_400 微元
    assert attempt[1] == 2_000_400
    receipt = conn.execute(
        "SELECT status, response_json, usage_json FROM receipt WHERE id=?",
        (ref.receipt_id,)).fetchone()
    assert receipt[0] == "received" and receipt[2] is not None


def test_record_response_without_usage_keeps_unsettled(env):
    conn, config = env
    ref = _authorize(conn, config)
    result = _ok_result()
    object.__setattr__(result, "usage", None)  # frozen dataclass 替换
    record_response(conn, config, ref, result)
    row = conn.execute(
        "SELECT status, actual_micro_cny FROM receipt_attempt WHERE id=?",
        (ref.attempt_id,)).fetchone()
    assert row[0] == "received" and row[1] is None  # actual NULL=未决,不 COALESCE


class _QueryCounter:
    def __init__(self, conn):
        self._conn = conn
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        return self._conn.execute(*args, **kwargs)


def test_snapshot_3settled_1pending_single_query(env):
    conn, config = env
    # 3 条已核清(9600+9600+100)+1 条 received 未核清(reserved 9600)
    for actual in (9600, 9600, 100):
        _seed_attempt(conn, reserved=actual, actual=actual)
    _seed_attempt(conn, reserved=9600, actual=None, status="received")
    counter = _QueryCounter(conn)
    cost, pending = issue_cost_snapshot(counter, "2026-10-06")
    assert counter.calls == 1                # 两值出自同一查询
    assert cost == pytest.approx(0.0289)     # 28900 微元
    assert pending is True

    # 核清最后一例为 9000 微元 → 28300 → ¥0.0283 / false
    conn.execute(
        "UPDATE receipt_attempt SET actual_micro_cny=9000 WHERE actual_micro_cny IS NULL")
    conn.commit()
    cost2, pending2 = issue_cost_snapshot(conn, "2026-10-06")
    assert cost2 == pytest.approx(0.0283) and pending2 is False


def test_snapshot_zero_attempt_issue(env):
    conn, config = env
    cost, pending = issue_cost_snapshot(conn, "2099-01-01")
    assert cost == 0.0 and pending is False


EVIDENCE_FULL = {
    "evidence_type": "bill_line",      # 类型[账单行/usage 复核]
    "ref": "bill-2026-10-L42",         # 关联标识
    "checked_utc": "2026-10-06T12:00:00Z",  # 核查时间
    "note": "账单行与 attempt 一一对应",     # 依据说明
}


def test_reconcile_missing_evidence_rejected(env):
    conn, config = env
    _seed_attempt(conn, reserved=9600, actual=None, status="unknown")
    attempt_id = conn.execute(
        "SELECT id FROM receipt_attempt WHERE actual_micro_cny IS NULL").fetchone()[0]
    for missing in ("evidence_type", "ref", "checked_utc", "note"):
        evidence = {k: v for k, v in EVIDENCE_FULL.items() if k != missing}
        ok = reconcile(conn, config, attempt_id, evidence,
                       actual_micro_cny=5000)
        assert ok is False
    row = conn.execute(
        "SELECT actual_micro_cny FROM receipt_attempt WHERE id=?",
        (attempt_id,)).fetchone()
    assert row[0] is None  # 证据缺失不得核清,保持未决


def test_reconcile_full_evidence_updates_projection(env):
    conn, config = env
    _seed_attempt(conn, reserved=9600, actual=None, status="unknown")
    attempt_id = conn.execute(
        "SELECT id FROM receipt_attempt WHERE actual_micro_cny IS NULL").fetchone()[0]
    ok = reconcile(conn, config, attempt_id, dict(EVIDENCE_FULL, ref="bill-L43"),
                   actual_micro_cny=5000)
    assert ok is True
    row = conn.execute(
        "SELECT actual_micro_cny, reconcile_json FROM receipt_attempt"
        " WHERE id=?", (attempt_id,)).fetchone()
    assert row[0] == 5000 and row[1] is not None
    month = conn.execute("SELECT * FROM api_usage").fetchall()
    assert len(month) >= 1                 # 月投影更新(报表,不作授权依据)


def test_reconcile_actual_over_reserved_pauses(env):
    conn, config = env
    _seed_attempt(conn, reserved=1000, actual=None, status="unknown")
    attempt_id = conn.execute(
        "SELECT id FROM receipt_attempt WHERE actual_micro_cny IS NULL").fetchone()[0]
    reconcile(conn, config, attempt_id, dict(EVIDENCE_FULL), actual_micro_cny=2000)
    paused = conn.execute(
        "SELECT value FROM engine_meta WHERE key='pay_paused'").fetchone()[0]
    assert paused == "1"                    # 实付超预占=停新增(持久化)


def test_record_response_usage_over_count_pauses(env):
    conn, config = env
    ref = _authorize(conn, config, token_count=500)  # 预占计数 500
    record_response(conn, config, ref,
                    _ok_result(prompt_tokens=2_000))  # usage 超 → 上界失效
    paused = conn.execute(
        "SELECT value FROM engine_meta WHERE key='pay_paused'").fetchone()[0]
    assert paused == "1"
    # 但先持久化再判定:attempt 已 received+结算
    row = conn.execute(
        "SELECT status FROM receipt_attempt WHERE id=?",
        (ref.attempt_id,)).fetchone()
    assert row[0] == "received"


def test_reuse_cost_attribution_across_issues(env):
    conn, config = env
    # 上期 attempt 已结算 ¥0.01(10000 微元),本期零 attempt
    _seed_attempt(conn, reserved=10000, actual=10000, issue_date="2026-10-05")
    cost_new, pending_new = issue_cost_snapshot(conn, "2026-10-06")
    assert cost_new == 0.0 and pending_new is False   # 复用不把旧费用计入新期
    cost_old, _ = issue_cost_snapshot(conn, "2026-10-05")
    assert cost_old == pytest.approx(0.01)            # 上期快照不变


# ---------- Task 8:request_hash / reusable_scores / compute_n_new(验收 1/2/3) ----------

import dataclasses

from nanmu_engine.config import PricingRow, RateLimits
from nanmu_engine.llm import LLMResult
from nanmu_engine.ledger import (
    apply_n_new,
    compute_n_new,
    request_hash,
    reusable_scores,
)

BASE_CTX = {
    "provider": "deepseek", "endpoint": "/chat/completions",
    "purpose": "score", "model": "deepseek-flash",
    "prompt_version": "pv-abc123",
    "system_text": "SYS-TEXT(模板实例化后)",
    "max_tokens": 200, "thinking": "disabled", "response_format": "json_object",
}


def _member(i, tier="T1"):
    return {"identity_key": f"url:https://example.com/{i}",
            "content_hash": f"chash-{i}", "entry_id": i,
            "user_text": f"标题:t{i}\n\n正文:\nbody-{i}",
            "source_tier": tier,
            "discovered_utc": f"2026-10-06T00:00:{i:02d}Z"}


def _ctx_for(member, ctx, tag):
    return dict(ctx, identity_key=member["identity_key"],
                content_hash=member["content_hash"],
                user_text=member["user_text"], attemptTag=tag)


def _seed_score_response(conn, config, member, ctx, tag="score-1",
                         content='{"attentionScore": 71}', finish="stop",
                         status="received"):
    ref = _authorize(conn, config,
                     request_hash=request_hash(_ctx_for(member, ctx, tag)),
                     identity_key=member["identity_key"], token_count=100)
    result = LLMResult(
        http_status=200, finish_reason=finish, content=content,
        json_parsed=False,
        usage={"prompt_tokens": 100, "prompt_cache_hit_tokens": 0,
               "prompt_cache_miss_tokens": 100, "completion_tokens": 10},
        provider_request_id="rid-1", error_message=None)
    record_response(conn, config, ref, result)
    if status == "completed":
        conn.execute("UPDATE receipt SET status='completed' WHERE id=?",
                     (ref.receipt_id,))
        conn.commit()
    return ref


def test_request_hash_changes_on_any_identity_field():
    base = dict(BASE_CTX, identity_key="url:x", content_hash="c1",
                user_text="u1", attemptTag="score-1")
    h1 = request_hash(base)
    assert h1 == request_hash(dict(base))       # 确定性
    for field, value in [("prompt_version", "pv-new"),
                         ("user_text", "u1 "),           # 截断后实际输入变
                         ("identity_key", "url:y"),
                         ("content_hash", "c2"),
                         ("attemptTag", "score-2"),
                         ("model", "deepseek-prod")]:
        assert request_hash(dict(base, **{field: value})) != h1, field


def test_reuse_matrix_acceptance_1(env):
    conn, config = env
    m = _member(1)
    # 同身份 completed → 可复用
    _seed_score_response(conn, config, m, BASE_CTX, "score-1", status="completed")
    snap = reusable_scores(conn, [m], BASE_CTX)
    assert snap["url:https://example.com/1"]["score_1"] is True

    # prompt 版本变 → 不可
    snap2 = reusable_scores(conn, [m], dict(BASE_CTX, prompt_version="pv-changed"))
    assert snap2["url:https://example.com/1"]["score_1"] is not True

    # 截断标记差异(实际输入变)→ 不可
    m_trunc = dict(m, user_text=m["user_text"] + "…[截断]")
    snap3 = reusable_scores(conn, [m_trunc], BASE_CTX)
    assert snap3["url:https://example.com/1"]["score_1"] is not True


def test_reuse_received_validation_acceptance_1(env):
    conn, config = env
    # received 过完整 E4 验证器 → 可
    m2 = _member(2)
    _seed_score_response(conn, config, m2, BASE_CTX, "score-1", status="received")
    snap = reusable_scores(conn, [m2], BASE_CTX)
    assert snap["url:https://example.com/2"]["score_1"] is True

    # received 不可解析 → 不可(走 E4)
    m3 = _member(3)
    _seed_score_response(conn, config, m3, BASE_CTX, "score-1",
                         content="not-json", status="received")
    snap = reusable_scores(conn, [m3], BASE_CTX)
    assert snap["url:https://example.com/3"]["score_1"] is not True

    # received 且 finish_reason=length 而 JSON 恰好可解析 → 不可
    m4 = _member(4)
    _seed_score_response(conn, config, m4, BASE_CTX, "score-1",
                         content='{"attentionScore": 6', finish="length",
                         status="received")
    snap = reusable_scores(conn, [m4], BASE_CTX)
    assert snap["url:https://example.com/4"]["score_1"] is not True


def test_partial_completion_needs_acceptance_3(env):
    conn, config = env
    m = _member(5)
    _seed_score_response(conn, config, m, BASE_CTX, "score-1", status="received")
    snap = reusable_scores(conn, [m], BASE_CTX)
    entry = snap["url:https://example.com/5"]
    assert entry["score_1"] is True and entry["score_2"] is not True
    assert entry["needs"] == ["score-2"]     # 只补缺失那条,不重发有效侧
    # score-2 已有 2 次失败 → 补发 attempt_no=3(顺延,重启不重置)
    rh2 = request_hash(_ctx_for(m, BASE_CTX, "score-2"))
    for origin in ("initial", "retry"):
        r = _authorize(conn, config, request_hash=rh2,
                       identity_key=m["identity_key"], origin=origin)
        record_failure(conn, config, r, "retryable",
                       {"http_status": 503, "matrix_code": "E3.http",
                        "message": "x"})
    r3 = _authorize(conn, config, request_hash=rh2,
                    identity_key=m["identity_key"], origin="retry")
    assert r3.attempt_no == 3


def test_apply_n_new_order_acceptance_2():
    members = [_member(i) for i in range(10)]
    snapshot = {m["identity_key"]: {
        "score_1": True if i < 4 else None,
        "score_2": True if i < 4 else None,
        "needs": [] if i < 4 else ["score-1", "score-2"]}
        for i, m in enumerate(members)}
    # 4 可复用 + 6 需新增;N_new=4 → 4 recoverable + 4 to_score + 2 capped
    out = apply_n_new(members, snapshot, n_new=4)
    assert len(out["recoverable"]) == 4
    assert len(out["to_score"]) == 4
    assert len(out["capped"]) == 2
    # 截断排序:T1 优先 → discovered_utc 降序 → identity_key 升序(确定性)
    assert out["to_score"][0]["identity_key"] == "url:https://example.com/9"
    # N_new=0 → 4 recoverable + 6 capped,无成员丢失
    out0 = apply_n_new(members, snapshot, n_new=0)
    assert len(out0["recoverable"]) == 4 and len(out0["to_score"]) == 0
    assert len(out0["capped"]) == 6
    total = {m["identity_key"] for m in
             out0["recoverable"] + out0["to_score"] + out0["capped"]}
    assert len(total) == 10


def test_compute_n_new_fixed_example(env):
    # 固定算例:期可用 1000000、max_entries 15、重试 200000/5、窗口 0 → N=34
    # (真配置:输入价 2M/输出 8M 微元/M、max_input 4000、max_output 200 → W=9600)
    conn, config = env
    assert compute_n_new(conn, config, issue_date="2026-10-06") == 34


def test_compute_n_new_negative_available(env):
    conn, config = env
    odd = dataclasses.replace(config.budget, per_issue_micro_cny=1)
    assert compute_n_new(conn, dataclasses.replace(config, budget=odd),
                         issue_date="2026-10-06") == 0


def test_compute_n_new_zero_price_unbounded_by_money(env):
    conn, config = env
    zero = dataclasses.replace(
        config.budget,
        pricing=(PricingRow("z", "deepseek-flash", 0, 0, 0),))
    # W=0 且期可用扣预留 ≥0 → 金额不设限,N 取次数项 40
    assert compute_n_new(conn, dataclasses.replace(config, budget=zero),
                         issue_date="2026-10-06") == 40


def test_compute_n_new_disabled_limit_is_zero(env):
    conn, config = env
    odd = dataclasses.replace(
        config.budget, rate_limits=RateLimits(10, 0, 400))
    assert compute_n_new(conn, dataclasses.replace(config, budget=odd),
                         issue_date="2026-10-06") == 0


def test_compute_n_new_retry_reserve_zero(env):
    conn, config = env
    odd = dataclasses.replace(config.budget, retry_reserve_micro_cny=0)
    # N_money=44,仍受 N_hour=40 限制
    assert compute_n_new(conn, dataclasses.replace(config, budget=odd),
                         issue_date="2026-10-06") == 40


# ---------- 修复轮(评审 C1/C2/I1-I4):停用语义/含本次预占/跨月未决/回执状态/月投影幂等/对账共用 ----------
# (旧 test_compute_n_new_cross_month_unknown 断言"跨月未决不扣本月"已删:
#  budget.md L67 推翻 Task 8 Ruling,新语义由 test_i1 覆盖)

import dataclasses as _dc

from nanmu_engine.config import RateLimits as _RateLimits


def test_c1_rate_limits_zero_disables_new_attempts(env):
    # 合法停用(budget 行任一档 ≤0)= 停止新增付费(E5),不是"该档不设限"
    conn, config = env
    odd = _dc.replace(config.budget, rate_limits=_RateLimits(10, 0, 400))
    odd_cfg = _dc.replace(config, budget=odd)
    sync_budget_limits(conn, odd_cfg)          # 停用配置同步进 budget 表
    result = _authorize(conn, odd_cfg)
    assert result.status == "rejected"
    assert result.reject_reason == "disabled"


def test_c1_monthly_zero_disables_new_attempts(env):
    conn, config = env
    odd = _dc.replace(config.budget, monthly_micro_cny=0)
    odd_cfg = _dc.replace(config, budget=odd)
    sync_budget_limits(conn, odd_cfg)
    result = _authorize(conn, odd_cfg)
    assert result.status == "rejected" and result.reject_reason == "disabled"


def test_c2_money_check_includes_new_reservation_month(env):
    # 存量 49_999_999 未达 50M,但 +本次预占 3_600 越线 → 拒
    # (种子行放在外月,期分支不触发,单独验证月边界)
    conn, config = env
    _seed_attempt(conn, minutes_ago=5, reserved=3_600, actual=49_999_999,
                  issue_date="2026-09-30")
    result = _authorize(conn, config)          # 默认 1000 tokens → reserved 3_600
    assert result.status == "rejected" and result.reject_reason == "money"


def test_c2_money_check_includes_new_reservation_issue(env):
    conn, config = env
    _seed_attempt(conn, minutes_ago=5, reserved=3_600, actual=999_990)
    result = _authorize(conn, config)
    assert result.status == "rejected" and result.reject_reason == "money"


def test_i1_cross_month_pending_counts_month_available(env):
    # budget.md:月可用扣**所有月份**尚未核清预占(跨月 unknown 保留直至核清)
    conn, config = env
    _seed_attempt(conn, minutes_ago=40 * 24 * 60, reserved=500_000,
                  actual=None, issue_date="2026-08-27", status="unknown")
    odd = _dc.replace(config.budget, monthly_micro_cny=1_000_000)
    odd_cfg = _dc.replace(config, budget=odd)
    # 月可用=1M−500_000=500_000;期可用=min(1M,500K)=500K
    # N_money=floor((500_000−144_000−200_000)/19_200)=8
    assert compute_n_new(conn, odd_cfg, issue_date="2026-10-06") == 8
    # authorize 同口径:月可用 0 余量 + 本次预占 → money 拒
    odd2 = _dc.replace(config.budget, monthly_micro_cny=500_000)
    result = _authorize(conn, _dc.replace(config, budget=odd2))
    assert result.status == "rejected" and result.reject_reason == "money"


def test_i2_record_failure_updates_receipt_status(env):
    conn, config = env
    result, _ = _run_attempt(conn, config, error_class="unknown")
    st = conn.execute("SELECT status FROM receipt WHERE id=?",
                      (result.receipt_id,)).fetchone()[0]
    assert st == "unknown"
    result2, _ = _run_attempt(conn, config, error_class="no_retry",
                              request_hash="g" * 64)
    st2 = conn.execute("SELECT status FROM receipt WHERE id=?",
                       (result2.receipt_id,)).fetchone()[0]
    assert st2 == "failed"


def test_i3_api_usage_recomputed_idempotent_after_reconcile(env):
    conn, config = env
    ref = _authorize(conn, config, token_count=1_000)
    record_response(conn, config, ref, _ok_result(prompt_tokens=100))
    before = conn.execute("SELECT cost_cny FROM api_usage").fetchone()[0]
    assert before == pytest.approx(0.0006)     # 结算 600 微元
    reconcile(conn, config, ref.attempt_id, dict(EVIDENCE_FULL),
              actual_micro_cny=1_000)
    mid = conn.execute("SELECT cost_cny FROM api_usage").fetchone()[0]
    reconcile(conn, config, ref.attempt_id, dict(EVIDENCE_FULL, ref="L44"),
              actual_micro_cny=1_000)          # 重复核清不双计
    after = conn.execute("SELECT cost_cny FROM api_usage").fetchone()[0]
    assert mid == after == pytest.approx(0.001)  # 幂等重算


def test_i4_record_failure_usage_over_count_pauses(env):
    conn, config = env
    ref = _authorize(conn, config, token_count=500)
    record_failure(conn, config, ref, "no_retry",
                   {"http_status": 400, "matrix_code": "E1.request",
                    "message": "bad"},
                   usage={"prompt_tokens": 2_000,
                          "prompt_cache_hit_tokens": 0,
                          "prompt_cache_miss_tokens": 2_000,
                          "completion_tokens": 5})
    paused = conn.execute(
        "SELECT value FROM engine_meta WHERE key='pay_paused'").fetchone()[0]
    assert paused == "1"                       # 失败路径同样对账停新增
    row = conn.execute("SELECT status FROM receipt_attempt WHERE id=?",
                       (ref.attempt_id,)).fetchone()
    assert row[0] == "failed"                  # 先落库后判定


# ---------- 审计修复轮(P1-1..P1-4):计费证据/金额上界/同事务暂停/上海自然月 ----------

def _raw_result(usage):
    return LLMResult(
        http_status=200, finish_reason="stop",
        content='{"attentionScore": 60}', json_parsed=True,
        usage=usage, provider_request_id="resp-x", error_message=None)


def _pay_paused(conn):
    return conn.execute(
        "SELECT value FROM engine_meta WHERE key='pay_paused'").fetchone()[0]


def test_p1_usage_without_billing_keys_not_settled(env):
    # P1-1:仅 total_tokens——输入输出计费证据均缺,不得核清为 0
    conn, config = env
    import json as _json
    ref = _authorize(conn, config, token_count=1200)
    record_response(conn, config, ref, _raw_result({"total_tokens": 1200}))
    row = conn.execute(
        "SELECT status, usage_json, actual_micro_cny FROM receipt_attempt"
        " WHERE id=?", (ref.attempt_id,)).fetchone()
    assert row[0] == "received"
    assert _json.loads(row[1]) == {"total_tokens": 1200}   # 原文保存
    assert row[2] is None                                 # 未决不核清
    cost, pending = issue_cost_snapshot(conn, "2026-10-06")
    assert pending is True and cost > 0                   # 保守取 reserved


def test_p1_usage_without_completion_not_settled(env):
    # P1-1:缺 completion_tokens——输出费用未知,不释放其预占
    conn, config = env
    ref = _authorize(conn, config, token_count=1000)
    record_response(conn, config, ref,
                    _raw_result({"prompt_tokens": 1000}))
    row = conn.execute("SELECT actual_micro_cny FROM receipt_attempt"
                       " WHERE id=?", (ref.attempt_id,)).fetchone()
    assert row[0] is None


def test_p1_usage_partial_cache_breakdown_not_settled(env):
    # P1-1:hit 有而 miss 缺——剩余输入 token 不可当零
    conn, config = env
    ref = _authorize(conn, config, token_count=1000)
    record_response(conn, config, ref, _raw_result(
        {"prompt_tokens": 1000, "prompt_cache_hit_tokens": 100,
         "completion_tokens": 10}))
    row = conn.execute("SELECT actual_micro_cny FROM receipt_attempt"
                       " WHERE id=?", (ref.attempt_id,)).fetchone()
    assert row[0] is None


def test_p1_incomplete_usage_not_settled_on_failure(env):
    # P1-1:失败路径同一套计费有效性判定
    conn, config = env
    import json as _json
    ref = _authorize(conn, config, token_count=1200)
    record_failure(conn, config, ref, "no_retry",
                   {"http_status": 400, "matrix_code": "E1.request",
                    "message": "bad"}, usage={"total_tokens": 1200})
    row = conn.execute(
        "SELECT status, usage_json, actual_micro_cny FROM receipt_attempt"
        " WHERE id=?", (ref.attempt_id,)).fetchone()
    assert row[0] == "failed"
    assert _json.loads(row[1]) == {"total_tokens": 1200}
    assert row[2] is None
    assert _pay_paused(conn) == "0"          # 无计费证据→无金额上界可对


def test_p1_actual_over_reserved_pauses_on_response(env):
    # P1-2:输入计量未超但实际金额超预占 → 同事务停新增
    conn, config = env
    ref = _authorize(conn, config, token_count=10)   # reserved=10×2+200×8=1620
    usage = {"prompt_tokens": 10, "prompt_cache_hit_tokens": 0,
             "prompt_cache_miss_tokens": 10, "completion_tokens": 201}
    record_response(conn, config, ref, _raw_result(usage))
    row = conn.execute("SELECT status, actual_micro_cny FROM receipt_attempt"
                       " WHERE id=?", (ref.attempt_id,)).fetchone()
    assert row == ("received", 1628)         # 10×2+201×8=1628,真实费用保留
    assert _pay_paused(conn) == "1"


def test_p1_actual_over_reserved_pauses_on_failure(env):
    # P1-2:失败结算路径同样受金额上界约束
    conn, config = env
    ref = _authorize(conn, config, token_count=10)
    usage = {"prompt_tokens": 10, "prompt_cache_hit_tokens": 0,
             "prompt_cache_miss_tokens": 10, "completion_tokens": 201}
    record_failure(conn, config, ref, "retryable",
                   {"http_status": 503, "matrix_code": "E3.http",
                    "message": "x"}, usage=usage)
    row = conn.execute("SELECT status, actual_micro_cny FROM receipt_attempt"
                       " WHERE id=?", (ref.attempt_id,)).fetchone()
    assert row == ("failed", 1628)
    assert _pay_paused(conn) == "1"


def test_p1_settle_and_pause_atomic_on_response(env, monkeypatch):
    # P1-3:结算、对账、暂停同一事务——中途崩溃全回滚,无部分状态
    import nanmu_engine.ledger as ledger_mod
    conn, config = env
    ref = _authorize(conn, config, token_count=10)

    def boom(c, reason):
        raise RuntimeError("crash before pause")
    monkeypatch.setattr(ledger_mod, "_pause_pay_sql", boom)
    usage = {"prompt_tokens": 10, "prompt_cache_hit_tokens": 0,
             "prompt_cache_miss_tokens": 10, "completion_tokens": 201}
    with pytest.raises(RuntimeError):
        record_response(conn, config, ref, _raw_result(usage))
    row = conn.execute("SELECT status, actual_micro_cny FROM receipt_attempt"
                       " WHERE id=?", (ref.attempt_id,)).fetchone()
    assert row == ("pending", None)          # 已结算状态不落库
    assert _pay_paused(conn) == "0"


def test_p1_settle_and_pause_atomic_on_reconcile(env, monkeypatch):
    # P1-3:人工核清同样单事务——核清与暂停同生同灭
    import nanmu_engine.ledger as ledger_mod
    conn, config = env
    _seed_attempt(conn, reserved=1000, actual=None, status="unknown")
    attempt_id = conn.execute(
        "SELECT id FROM receipt_attempt WHERE actual_micro_cny IS NULL"
    ).fetchone()[0]

    def boom(c, reason):
        raise RuntimeError("crash before pause")
    monkeypatch.setattr(ledger_mod, "_pause_pay_sql", boom)
    with pytest.raises(RuntimeError):
        reconcile(conn, config, attempt_id, dict(EVIDENCE_FULL),
                  actual_micro_cny=2000)
    row = conn.execute("SELECT actual_micro_cny, reconcile_json"
                       " FROM receipt_attempt WHERE id=?",
                       (attempt_id,)).fetchone()
    assert row == (None, None)
    assert _pay_paused(conn) == "0"


def test_p1_shanghai_natural_month_boundary(env):
    # P1-4:月口径=Asia/Shanghai 自然月(非 UTC 月)。
    # 上海 2026-11-01 08:30(=UTC 11-01 00:30)调度;上海 11-01 00:10
    # 的消费存为 UTC 10-31T16:10Z——属上海 11 月,须占本月额度。
    conn, config = env
    now = dt.datetime(2026, 11, 1, 0, 30, tzinfo=dt.timezone.utc)
    odd = _dc.replace(config.budget, monthly_micro_cny=3000)
    odd_cfg = _dc.replace(config, budget=odd)
    # 上海 10-31 23:59(=UTC 15:59)属 10 月 → 不占 11 月 → 放行
    _seed_attempt(conn, started_utc="2026-10-31T15:59:00Z",
                  reserved=2000, actual=2000, issue_date="2026-10-30")
    ok = _authorize(conn, odd_cfg, now=now, token_count=10)
    assert ok.status == "reserved"
    # 上海 11-01 00:10(=UTC 16:10)属 11 月:2000+1620>3000 → 拒
    _seed_attempt(conn, started_utc="2026-10-31T16:10:00Z",
                  reserved=2000, actual=2000, issue_date="2026-10-31")
    rejected = _authorize(conn, odd_cfg, now=now, token_count=10,
                          request_hash="g" * 64)
    assert rejected.status == "rejected"
    assert rejected.reject_reason == "money"


def test_p1_shanghai_month_in_compute_n_new(env):
    conn, config = env
    # now=上海 11-02 08:30(距跨界行 >24h,不进 day 窗口)
    now = dt.datetime(2026, 11, 2, 0, 30, tzinfo=dt.timezone.utc)
    _seed_attempt(conn, started_utc="2026-10-31T16:10:00Z",
                  reserved=200_000, actual=200_000, issue_date="2026-10-31")
    odd = _dc.replace(config.budget, monthly_micro_cny=1_000_000)
    odd_cfg = _dc.replace(config, budget=odd)
    # 月可用=1M−200_000=800_000 → N_money=(800_000−344_000)//19_200=23
    # (若按 UTC 月归 10 月则得固定算例 34——本测试钉死两种口径差异)
    assert compute_n_new(conn, odd_cfg, "2026-11-02", now=now) == 23


def test_p1_shanghai_month_in_api_usage_projection(env):
    # P1-4:月投影与授权同口径(上海自然月)
    conn, config = env
    _seed_attempt(conn, started_utc="2026-10-31T16:10:00Z",
                  reserved=2000, actual=2000, issue_date="2026-10-31")
    ref = _authorize(conn, config, token_count=1000)
    record_response(conn, config, ref, _ok_result(prompt_tokens=1000))
    months = {r[0] for r in conn.execute("SELECT month FROM api_usage")}
    assert "2026-11" in months              # 跨界行按上海月归 11 月
