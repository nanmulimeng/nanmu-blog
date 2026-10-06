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

import functools
import hashlib
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
    return f"{PROVIDER}{ENDPOINT}/{purpose}/{model}/{request_hash}"


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
        if origin == "unknown_retry":
            # 与 receipt.unknown_retry_used 同事务双写(判定读标志、审计按行重算)
            conn.execute(
                "UPDATE receipt SET unknown_retry_used=1 WHERE id=?",
                (receipt_id,))
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


# ---------- 失败持久化与再发送三条件(Task 6;model-calls §3 规则 5) ----------

@dataclass(frozen=True)
class RetryVerdict:
    allowed: bool
    channel: str | None     # 'normal' | 'unknown_retry' | None
    reason: str | None


def _pricing_for(config: Config, model: str):
    for row in config.budget.pricing:
        if row.model == model:
            return row
    raise KeyError(f"价目缺失:{model}")


def _settle_micro_cny(config: Config, model: str, usage: dict) -> int:
    """按价目结算整数微元:命中×缓存价+未命中×输入价+补全×输出价,向上取整。"""
    price = _pricing_for(config, model)
    hit = usage.get("prompt_cache_hit_tokens", 0) or 0
    miss = usage.get("prompt_cache_miss_tokens", 0) or 0
    if not hit and not miss:
        miss = usage.get("prompt_tokens", 0) or 0  # 缺分项保守按未缓存全量
    completion = usage.get("completion_tokens", 0) or 0
    micro = (hit * price.cached_input_per_mtok_micro_cny
             + miss * price.input_per_mtok_micro_cny
             + completion * price.output_per_mtok_micro_cny)
    return math.ceil(micro / _MICRO_PER_MILLION)


def record_failure(conn: sqlite3.Connection, config: Config,
                   ref: AuthorizeResult, error_class: str,
                   fail_detail: dict, usage: dict | None = None) -> None:
    """单事务失败落库:attempt→failed/unknown + error_class + fail_detail_json
    同事务写;有 usage 先结算。**不触碰 attempt_origin(预占后不可改写)**。"""
    status = "unknown" if error_class == "unknown" else "failed"
    detail_json = json.dumps(fail_detail, ensure_ascii=False, sort_keys=True)
    with conn:
        if usage:
            conn.execute(
                "UPDATE receipt_attempt SET status=?, error_class=?,"
                " fail_detail_json=?, usage_json=?, actual_micro_cny=?"
                " WHERE id=?",
                (status, error_class, detail_json, json.dumps(usage),
                 _settle_micro_cny(config, _attempt_model(conn, ref), usage),
                 ref.attempt_id))
        else:
            conn.execute(
                "UPDATE receipt_attempt SET status=?, error_class=?,"
                " fail_detail_json=? WHERE id=?",
                (status, error_class, detail_json, ref.attempt_id))


def _attempt_model(conn: sqlite3.Connection, ref: AuthorizeResult) -> str:
    return conn.execute(
        "SELECT model FROM receipt WHERE id=?", (ref.receipt_id,)).fetchone()[0]


def can_retry(conn: sqlite3.Connection, config: Config, logical_key: str,
              now_utc: datetime) -> RetryVerdict:
    """再发送三条件判定,输入全部来自持久化列(落库重放,无内存依赖)。

    判定序:在途/已收到 → error_class=no_retry 硬停 → 硬上限(总行数
    < max_attempts+1)→ 最新 unknown 的专属通道(used=0 且 ≥30min)→
    普通通道(origin∈{initial,retry} 行数 < max_attempts,不按
    error_class 过滤;两类不互借)。
    """
    receipt = conn.execute(
        "SELECT id, unknown_retry_used FROM receipt WHERE logical_key=?",
        (logical_key,)).fetchone()
    if receipt is None:
        return RetryVerdict(False, None, "unknown_logical_key")
    receipt_id, unknown_used = receipt

    rows = conn.execute(
        "SELECT id, attempt_no, status, attempt_origin, error_class,"
        " started_utc FROM receipt_attempt WHERE receipt_id=?"
        " ORDER BY attempt_no", (receipt_id,)).fetchall()
    if not rows:
        return RetryVerdict(False, None, "no_attempts")
    latest = rows[-1]

    if latest[2] == "pending":
        return RetryVerdict(False, None, "attempt_in_flight")
    if latest[2] == "received":
        return RetryVerdict(False, None, "already_received")
    if latest[4] == "no_retry":
        return RetryVerdict(False, None, "error_class_no_retry")

    max_attempts = config.budget.max_attempts
    hard_cap = max_attempts + 1
    if len(rows) >= hard_cap:
        return RetryVerdict(False, None, "hard_cap")

    if latest[4] == "unknown":
        if unknown_used:
            return RetryVerdict(False, None, "unknown_retry_used")
        started = datetime.strptime(latest[5], "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc)
        if now_utc - started < timedelta(minutes=config.budget.unknown_retry_after_min):
            return RetryVerdict(False, None, "unknown_wait")
        return RetryVerdict(True, "unknown_retry", None)

    normal_used = sum(1 for r in rows if r[3] in ("initial", "retry"))
    if normal_used >= max_attempts:
        return RetryVerdict(False, None, "normal_quota_exhausted")
    return RetryVerdict(True, "normal", None)


# ---------- 结算、核清与期费用快照(Task 7;model-calls 验收 7/8/9/10) ----------

_EVIDENCE_KEYS = ("evidence_type", "ref", "checked_utc", "note")


def _pause_pay(conn: sqlite3.Connection, reason: str) -> None:
    """置 pay_paused=1 持久化停新增并记录原因(对账硬失败;同解除协议)。"""
    now = _utc_now()
    with conn:
        conn.execute(
            "INSERT INTO engine_meta (key, value, updated_utc)"
            " VALUES ('pay_paused', '1', ?)"
            " ON CONFLICT(key) DO UPDATE SET value='1', updated_utc=excluded.updated_utc",
            (now,))
        conn.execute(
            "INSERT INTO engine_meta (key, value, updated_utc)"
            " VALUES ('pay_paused_reason', ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
            " updated_utc=excluded.updated_utc", (reason, now))


def _update_api_usage(conn: sqlite3.Connection, model: str,
                      tokens_in: int, tokens_out: int, micro: int) -> None:
    """月度成本聚合投影(报表;不作调用授权依据)。"""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    with conn:
        conn.execute(
            "INSERT INTO api_usage (month, provider, model, tokens_in,"
            " tokens_out, cost_cny) VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(month, provider, model) DO UPDATE SET"
            " tokens_in=tokens_in+excluded.tokens_in,"
            " tokens_out=tokens_out+excluded.tokens_out,"
            " cost_cny=cost_cny+excluded.cost_cny",
            (month, PROVIDER, model, tokens_in, tokens_out,
             micro / _MICRO_PER_MILLION))


def record_response(conn: sqlite3.Connection, config: Config,
                    ref: AuthorizeResult, result) -> None:
    """收到响应:先持久化 received+usage_json+结算,再谈解析与对账。

    response_json 存三要素对象 {content, finish_reason,
    provider_request_id}(design.md"显式保存 finish_reason、usage 与请求
    ID";列注释"供业务复用"——复用判定的 E4 验证器读它)。
    usage 缺失→actual 保持 NULL(未决,不 COALESCE 释放预算)。
    usage.prompt_tokens 超预占计数(请求身份 digest 内)→置 pay_paused=1
    持久化停新增(上界失效;规则 2),attempt 已先落 received。
    """
    model = _attempt_model(conn, ref)
    usage = getattr(result, "usage", None)
    response_json = json.dumps(
        {"content": getattr(result, "content", None),
         "finish_reason": getattr(result, "finish_reason", None),
         "provider_request_id": getattr(result, "provider_request_id", None)},
        ensure_ascii=False, sort_keys=True)
    with conn:
        if usage:
            micro = _settle_micro_cny(config, model, usage)
            conn.execute(
                "UPDATE receipt_attempt SET status='received', usage_json=?,"
                " actual_micro_cny=? WHERE id=?",
                (json.dumps(usage), micro, ref.attempt_id))
            conn.execute(
                "UPDATE receipt SET status='received', response_json=?,"
                " usage_json=?, cost_cny=?, completed_utc=? WHERE id=?",
                (response_json, json.dumps(usage), micro / _MICRO_PER_MILLION,
                 _utc_now(), ref.receipt_id))
        else:
            conn.execute(
                "UPDATE receipt_attempt SET status='received' WHERE id=?",
                (ref.attempt_id,))
            conn.execute(
                "UPDATE receipt SET status='received', response_json=?,"
                " completed_utc=? WHERE id=?",
                (response_json, _utc_now(), ref.receipt_id))
    if usage:
        _update_api_usage(conn, model,
                          usage.get("prompt_tokens", 0) or 0,
                          usage.get("completion_tokens", 0) or 0, micro)
        # 对账:超预占计数=上界失效(先持久化,后判定)
        digest = conn.execute(
            "SELECT request_digest FROM receipt WHERE id=?",
            (ref.receipt_id,)).fetchone()[0]
        token_count = json.loads(digest).get("token_count")
        prompt_tokens = usage.get("prompt_tokens")
        if token_count is not None and prompt_tokens is not None \
                and prompt_tokens > token_count:
            _pause_pay(
                conn,
                f"usage.prompt_tokens({prompt_tokens})>预占计数({token_count})"
                f" receipt={ref.receipt_id} attempt={ref.attempt_id}")


def reconcile(conn: sqlite3.Connection, config: Config, attempt_id: int,
              evidence: dict, *, actual_micro_cny: int) -> bool:
    """核清:证据四要素齐才单事务 UPDATE actual+reconcile_json。

    证据不足→False 保持未决(不得凭"应该没扣费"填 0);供应商实付超
    预占→置 pay_paused=1 停新增。receipt.cost_cny 投影顺带更新(可重算)。
    """
    missing = [k for k in _EVIDENCE_KEYS if not evidence.get(k)]
    if missing:
        return False
    row = conn.execute(
        "SELECT reserved_micro_cny, issue_date, receipt_id FROM receipt_attempt"
        " WHERE id=?", (attempt_id,)).fetchone()
    if row is None:
        return False
    reserved, issue_date, receipt_id = row
    reconcile_json = json.dumps(evidence, ensure_ascii=False, sort_keys=True)
    with conn:
        conn.execute(
            "UPDATE receipt_attempt SET actual_micro_cny=?, reconcile_json=?"
            " WHERE id=?", (actual_micro_cny, reconcile_json, attempt_id))
        # 投影顺带更新:该 receipt 全部已核清 actual 之和(可重算修复)
        total = conn.execute(
            "SELECT COALESCE(SUM(actual_micro_cny), 0) FROM receipt_attempt"
            " WHERE receipt_id=?", (receipt_id,)).fetchone()[0]
        conn.execute(
            "UPDATE receipt SET cost_cny=? WHERE id=?",
            (total / _MICRO_PER_MILLION, receipt_id))
    if actual_micro_cny > reserved:
        _pause_pay(conn, f"供应商实付({actual_micro_cny})>预占({reserved})"
                         f" attempt={attempt_id}")
    usage_row = conn.execute(
        "SELECT usage_json FROM receipt_attempt WHERE id=?",
        (attempt_id,)).fetchone()[0]
    tokens_in = tokens_out = 0
    if usage_row:
        usage = json.loads(usage_row)
        tokens_in = usage.get("prompt_tokens", 0) or 0
        tokens_out = usage.get("completion_tokens", 0) or 0
    model = conn.execute(
        "SELECT model FROM receipt WHERE id=?", (receipt_id,)).fetchone()[0]
    _update_api_usage(conn, model, tokens_in, tokens_out, actual_micro_cny)
    return True


def issue_cost_snapshot(conn, issue_date: str) -> tuple[float, bool]:
    """期费用快照:同一时点同一只读聚合查询。

    cost_cny=Σ(已核清 actual,未核清 reserved 保守值);
    cost_pending=存在任一 actual IS NULL(不限 status)。
    零 attempt 期=(0.0, False)。
    """
    row = conn.execute(
        "SELECT COALESCE(SUM(COALESCE(actual_micro_cny, reserved_micro_cny)), 0),"
        " EXISTS(SELECT 1 FROM receipt_attempt WHERE issue_date=?"
        " AND actual_micro_cny IS NULL)"
        " FROM receipt_attempt WHERE issue_date=?",
        (issue_date, issue_date)).fetchone()
    return row[0] / _MICRO_PER_MILLION, bool(row[1])


# ---------- 请求身份、复用判定与 N_new(Task 8;model-calls 验收 1/2/3) ----------

def request_hash(identity_ctx: dict) -> str:
    """sha256(确定性序列化)——model-calls §3 规则 2 的完整请求身份:
    provider/endpoint/purpose/model/prompt_version/模板实例化后完整
    system+user 文本(截断后实际输入)/max_tokens/thinking/response_format/
    identity_key/content_hash/attemptTag。任一字段变→哈希变。"""
    payload = json.dumps(identity_ctx, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _passes_e4(purpose: str, response_json: str | None) -> bool:
    """完整 E4 业务验证器(契约桩;Task 13/14 落地真验证器后回跑本测试)。

    桩契约:finish_reason=stop + content JSON 可解析为对象 + purpose 对应
    字段齐(score:attentionScore 为 0-100 整数;understand:title_zh/
    summary/reason 非空字符串)。length 即使 JSON 恰好可解析也不可。
    """
    if not response_json:
        return False
    try:
        envelope = json.loads(response_json)
    except (ValueError, TypeError):
        return False
    if not isinstance(envelope, dict) or envelope.get("finish_reason") != "stop":
        return False
    try:
        payload = json.loads(envelope.get("content") or "")
    except (ValueError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    if purpose == "score":
        score = payload.get("attentionScore")
        return type(score) is int and 0 <= score <= 100
    return all(isinstance(payload.get(k), str) and payload.get(k)
               for k in ("title_zh", "summary", "reason"))


def reusable_scores(conn: sqlite3.Connection, members: list[dict],
                    identity_ctx: dict) -> dict:
    """复用快照(只读零副作用;model-calls §3 规则 3)。

    有效性 = 完整请求身份匹配(identity_ctx+成员字段+attemptTag 哈希出
    logical_key)+ receipt.status∈{received, completed} + 过完整 E4 业务
    验证器。输出 = {identity_key → {score_1, score_2, needs(待补
    attemptTag), analysis_ref}};本期同身份 analysis 行同等视为有效进度。
    """
    purpose = identity_ctx["purpose"]
    model = identity_ctx["model"]
    tags = (("score-1", "score_1"), ("score-2", "score_2"))
    out: dict = {}
    for member in members:
        entry = {"score_1": None, "score_2": None, "needs": [],
                 "analysis_ref": None}
        for tag, key in tags:
            ctx = dict(identity_ctx, identity_key=member["identity_key"],
                       content_hash=member["content_hash"],
                       user_text=member["user_text"], attemptTag=tag)
            row = conn.execute(
                "SELECT status, response_json FROM receipt WHERE logical_key=?",
                (_logical_key(purpose, model, request_hash(ctx)),)).fetchone()
            if row is not None and row[0] in ("received", "completed"):
                entry[key] = _passes_e4(purpose, row[1])
        entry["needs"] = [t for t, k in tags if entry[k] is not True]
        analysis = conn.execute(
            "SELECT id FROM analysis WHERE entry_id=? AND prompt_version=?"
            " AND model=?", (member["entry_id"],
                             identity_ctx["prompt_version"], model)
        ).fetchone()
        if analysis is not None:
            entry["analysis_ref"] = analysis[0]
        out[member["identity_key"]] = entry
    return out


def _candidate_cmp(a: dict, b: dict) -> int:
    """截断排序:T1 优先 → discovered_utc 降序 → identity_key 升序
    (确定性;与 selection.md 展示排序不同用途,不混用)。"""
    rank = {"T1": 0, "T2": 1}
    ra, rb = rank.get(a.get("source_tier"), 1), rank.get(b.get("source_tier"), 1)
    if ra != rb:
        return ra - rb
    da, db = a.get("discovered_utc", ""), b.get("discovered_utc", "")
    if da != db:
        return -1 if da > db else 1
    ka, kb = a["identity_key"], b["identity_key"]
    return -1 if ka < kb else (1 if ka > kb else 0)


def apply_n_new(members: list[dict], reuse_snapshot: dict, *, n_new: int) -> dict:
    """N_new 作用顺序(model-calls 验收 2;data-ingestion 规则 8 单义):
    recoverable=至少一条当前请求身份有效的评分响应(评分网络零新增,
    部分完成 needs 只补缺失)——不占 N、不被截断;确需新增付费评分的
    成员按确定性排序截断前 n_new;其余 capped(不丢弃,留待下期)。"""
    recoverable, to_score = [], []
    for member in members:
        snap = reuse_snapshot.get(member["identity_key"], {})
        if snap.get("score_1") is True or snap.get("score_2") is True:
            recoverable.append(member)
        else:
            to_score.append(member)
    ordered = sorted(to_score, key=functools.cmp_to_key(_candidate_cmp))
    return {"recoverable": recoverable, "to_score": ordered[:n_new],
            "capped": ordered[n_new:]}


def compute_n_new(conn: sqlite3.Connection, config: Config,
                  issue_date: str) -> int:
    """候选上限公式本体(design.md"候选上限与额度预留"节,不复制口径
    之外的行为):先扣摘要与重试预留,再算评分容量;禁止除零;合法停用
    直接 N=0(允许零网络复用)。"""
    budget = config.budget
    rate = budget.rate_limits
    # 合法停用:金额(monthly/per_issue 任一 ≤0)或次数(hour/day 任一 ≤0)
    if (budget.monthly_micro_cny <= 0 or budget.per_issue_micro_cny <= 0
            or rate.per_hour <= 0 or rate.per_day <= 0):
        return 0

    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    month_used, issue_used = _money_used(conn, month=month, issue_date=issue_date)
    month_available = budget.monthly_micro_cny - month_used
    issue_available = min(budget.per_issue_micro_cny - issue_used,
                          month_available)
    counts = _window_counts(conn, now)

    price = _pricing_for(config, budget.default_model)
    numerator = (budget.max_input_tokens * price.input_per_mtok_micro_cny
                 + budget.max_output_tokens * price.output_per_mtok_micro_cny)
    w_score = (numerator + _MICRO_PER_MILLION - 1) // _MICRO_PER_MILLION
    w_summ = w_score            # M1 评分/摘要共用全局 token 上限
    reserved_micro = (issue_available
                      - config.selection.max_entries * w_summ
                      - budget.retry_reserve_micro_cny)

    if w_score == 0:
        # 已核实免费价:余量扣预留 ≥0 → 金额不设限,否则 0(禁除零)
        n_money = None if reserved_micro >= 0 else 0
    else:
        n_money = reserved_micro // (2 * w_score)
    n_hour = ((rate.per_hour - counts["hour"] - config.selection.max_entries
               - budget.retry_reserve_count) // 2)
    n_day = ((rate.per_day - counts["day"] - config.selection.max_entries
              - budget.retry_reserve_count) // 2)
    candidates = [n for n in (n_money, n_hour, n_day) if n is not None]
    return max(0, min(candidates))
