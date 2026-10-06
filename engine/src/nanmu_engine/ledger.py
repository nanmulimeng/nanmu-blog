"""授权闸门:一切新增付费 attempt 唯一经此(model-calls §3 规则 1)。

短事务 BEGIN IMMEDIATE → 检查(pay_paused → 窗口 → 金额)→ 写
receipt_attempt(pending+reserved+attempt_origin+issue_date+pricing_version,
首 attempt 同事务建 receipt 行)→ COMMIT,**之后**才允许出网。
拒绝不写任何行。复用/结算/只读不经此闸门。

预占公式(budget.md 第四轮定稿):预占 = ceil(输入预占 token 数 ×
峰时未缓存输入价 + max_output_tokens × 输出价),向上取整为整数微元;
输入预占 token 数 = ceil(计数 × 校准系数)(初始系数 1.0,官方资源;
校准记录绑定与状态检查在 Task 22 校准通道)。
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from nanmu_engine.config import BudgetConfig, Config

PROVIDER = "deepseek"
ENDPOINT = "/chat/completions"
_MICRO_PER_MILLION = 1_000_000

Origin = Literal["initial", "retry", "unknown_retry"]
RejectReason = Literal["pay_paused", "key_missing", "window", "money",
                       "token_count_unavailable"]


@dataclass(frozen=True)
class AuthorizeResult:
    status: str                      # 'reserved' | 'rejected'
    reject_reason: str | None
    receipt_id: int | None = None
    attempt_id: int | None = None
    attempt_no: int | None = None
    reserved_micro_cny: int | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _logical_key(purpose: str, model: str, request_hash: str) -> str:
    return f"{PROVIDER}/{ENDPOINT}/{purpose}/{model}/{request_hash}"


def sync_budget_limits(conn: sqlite3.Connection, config: Config) -> None:
    """把 budget.yaml 次数限额同步进 budget 表(budget.yaml 是预算真相源;
    行缺失=配置错误,拒绝付费)。"""
    rate = config.budget.rate_limits
    with conn:
        conn.execute(
            "INSERT INTO budget (service, per_minute, per_hour, per_day)"
            " VALUES ('llm', ?, ?, ?)"
            " ON CONFLICT(service) DO UPDATE SET"
            " per_minute=excluded.per_minute, per_hour=excluded.per_hour,"
            " per_day=excluded.per_day",
            (rate.per_minute, rate.per_hour, rate.per_day))


def _reserved_micro(config: Config, model: str, token_count: int) -> int:
    """预占金额(整数微元,含输出上限)。"""
    pricing = None
    for row in config.budget.pricing:
        if row.model == model:
            pricing = row
            break
    if pricing is None:
        raise KeyError(f"价目缺失:{model}(config 校验应已排除)")
    calibration_factor = 1.0   # 官方资源初始系数(model-calls 规则 11)
    input_tokens = math.ceil(token_count * calibration_factor)
    micro = (input_tokens * pricing.input_per_mtok_micro_cny
             + config.budget.max_output_tokens * pricing.output_per_mtok_micro_cny)
    return math.ceil(micro / _MICRO_PER_MILLION)


def _window_counts(conn: sqlite3.Connection, now: datetime) -> dict[str, int]:
    def since(delta: timedelta) -> int:
        cutoff = (now - delta).strftime("%Y-%m-%dT%H:%M:%SZ")
        return conn.execute(
            "SELECT COUNT(*) FROM receipt_attempt WHERE started_utc >= ?",
            (cutoff,)).fetchone()[0]
    return {
        "minute": since(timedelta(minutes=1)),
        "hour": since(timedelta(hours=1)),
        "day": since(timedelta(days=1)),
    }


def _money_used(conn: sqlite3.Connection, *, month: str,
                issue_date: str | None) -> tuple[int, int]:
    """返回 (当月已用微元, 当期已用微元);已结算+全部未决预占。"""
    month_total = conn.execute(
        "SELECT COALESCE(SUM(COALESCE(actual_micro_cny, reserved_micro_cny)), 0)"
        " FROM receipt_attempt WHERE started_utc LIKE ? || '%'", (month,)).fetchone()[0]
    issue_total = 0
    if issue_date:
        issue_total = conn.execute(
            "SELECT COALESCE(SUM(COALESCE(actual_micro_cny, reserved_micro_cny)), 0)"
            " FROM receipt_attempt WHERE issue_date = ?", (issue_date,)).fetchone()[0]
    return month_total, issue_total


def authorize(conn: sqlite3.Connection, config: Config, *, purpose: str,
              model: str, request_hash: str, identity_key: str,
              token_count: int | None, issue_date: str | None,
              origin: Origin) -> AuthorizeResult:
    """授权检查与预占写入(短事务;COMMIT 后才允许出网)。

    检查序:pay_paused(仅显式 '0' 放行,'1' 或键缺失拒绝)→ budget 行
    缺失(key_missing)→ 计数可得性 → 窗口次数 → 金额(已结算+未决预占)。
    """
    if token_count is None or token_count < 0:
        return AuthorizeResult("rejected", "token_count_unavailable")

    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    logical_key = _logical_key(purpose, model, request_hash)
    reserved = _reserved_micro(config, model, token_count)
    digest = json.dumps(
        {"purpose": purpose, "model": model, "identity_key": identity_key,
         "request_hash": request_hash, "token_count": token_count},
        ensure_ascii=False, sort_keys=True)

    try:
        conn.execute("BEGIN IMMEDIATE")
        # 1) pay_paused:仅显式 '0' 放行
        row = conn.execute(
            "SELECT value FROM engine_meta WHERE key='pay_paused'").fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            return AuthorizeResult("rejected", "key_missing")
        if row[0] != "0":
            conn.execute("ROLLBACK")
            return AuthorizeResult("rejected", "pay_paused")
        # 2) budget 行(次数限额真相源在表,行缺失=配置错误)
        rate_row = conn.execute(
            "SELECT per_minute, per_hour, per_day FROM budget"
            " WHERE service='llm'").fetchone()
        if rate_row is None:
            conn.execute("ROLLBACK")
            return AuthorizeResult("rejected", "key_missing")
        # 3) 窗口次数(receipt_attempt 聚合;复用不写行自然不计)
        counts = _window_counts(conn, now)
        if (rate_row[0] > 0 and counts["minute"] >= rate_row[0]
                or rate_row[1] > 0 and counts["hour"] >= rate_row[1]
                or rate_row[2] > 0 and counts["day"] >= rate_row[2]):
            conn.execute("ROLLBACK")
            return AuthorizeResult("rejected", "window")
        # 4) 金额:月度 + 单期(已结算+全部未决预占)
        month_used, issue_used = _money_used(
            conn, month=month, issue_date=issue_date)
        money = config.budget
        if (money.monthly_micro_cny > 0
                and month_used >= money.monthly_micro_cny
                or money.per_issue_micro_cny > 0 and issue_date
                and issue_used >= money.per_issue_micro_cny):
            conn.execute("ROLLBACK")
            return AuthorizeResult("rejected", "money")
        # 5) 写入:首 attempt 同事务建 receipt 行
        receipt = conn.execute(
            "SELECT id FROM receipt WHERE logical_key=?", (logical_key,)
        ).fetchone()
        if receipt is None:
            cur = conn.execute(
                "INSERT INTO receipt (logical_key, provider, endpoint,"
                " request_hash, service, purpose, model, status, request_digest,"
                " created_utc) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (logical_key, PROVIDER, ENDPOINT, request_hash, "llm", purpose,
                 model, "pending", digest, _utc_now()))
            receipt_id = cur.lastrowid
            attempt_no = 1
        else:
            receipt_id = receipt[0]
            attempt_no = conn.execute(
                "SELECT COALESCE(MAX(attempt_no), 0) + 1 FROM receipt_attempt"
                " WHERE receipt_id=?", (receipt_id,)).fetchone()[0]
        pricing_version = config.budget.pricing_version
        cur = conn.execute(
            "INSERT INTO receipt_attempt (receipt_id, attempt_no, issue_date,"
            " started_utc, status, attempt_origin, reserved_micro_cny,"
            " pricing_version) VALUES (?,?,?,?, 'pending', ?, ?, ?)",
            (receipt_id, attempt_no, issue_date, _utc_now(), origin,
             reserved, pricing_version))
        attempt_id = cur.lastrowid
        conn.execute("COMMIT")
        return AuthorizeResult("reserved", None, receipt_id=receipt_id,
                               attempt_id=attempt_id, attempt_no=attempt_no,
                               reserved_micro_cny=reserved)
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
