"""双次评分(score-1/score-2)与 E4 完整业务验证器。

链路(content-editing §3 规则 2/5/8):构造完整请求→tokenizer 迭代截断
(计数不可得不出网,不回退字符估算)→授权→出网→结算→单事务业务回写
(receipt×2 completed + analysis 行 + entry→scored)。评分与入选判断分离:
selected/claim 由入选判断(Task 15)按当期门槛/override 重新计算。

E4 验证器在此定稿(design.md 错误矩阵为真相源)并回填 Task 8 桩
(ledger._passes_e4 score 分支);understand 分支由 Task 14 落地后回填。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from nanmu_engine.config import Config, ConfigError
from nanmu_engine.llm import LLMRequest, call_llm, classify_failure
from nanmu_engine.ledger import (
    ENDPOINT,
    PROVIDER,
    _logical_key,
    authorize,
    can_retry,
    recover_stale_pending,
    record_failure,
    record_response,
    request_hash,
)
from nanmu_engine.token_count import (
    TokenizerUnavailable,
    count_request_tokens,
)

_TRUNCATE_MARK = "[...truncated]"
_MIN_USER = "标题:\n\n正文:\n"       # 最小标题空间(空标题+结构骨架)

ScoreTag = ("score-1", "score-2")


@dataclass(frozen=True)
class ScoreOutcome:
    status: str                      # completed/retryable/unknown/failed/rejected/excluded
    score_1: int | None = None
    score_2: int | None = None
    analysis_id: int | None = None
    receipt_ids: tuple[int, ...] = ()
    reason: str | None = None        # rejected/excluded 原因(gate:*/tokenizer_unavailable/title_too_long)


# ---------- E4 完整业务验证器(score 定稿) ----------

def validate_score_response(response_json: str | None) -> bool:
    """有效性 = finish_reason=stop(E4.terminal 非 stop 即使 JSON 恰好可
    解析也不可消费)+ content 非空合法 JSON 对象 + attentionScore 为
    0-100 整数(E4.parse:空/非法/缺字段/越界/类型不符)。多余字段不在
    失败清单(design.md E4 只列缺字段,不列多字段)。"""
    if not response_json:
        return False
    try:
        envelope = json.loads(response_json)
    except (ValueError, TypeError):
        return False
    if not isinstance(envelope, dict):
        return False
    if envelope.get("finish_reason") != "stop":
        return False
    try:
        payload = json.loads(envelope.get("content") or "")
    except (ValueError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    score = payload.get("attentionScore")
    return type(score) is int and 0 <= score <= 100


def _score_from_response(response_json: str) -> int:
    return json.loads(json.loads(response_json)["content"])["attentionScore"]


# ---------- prompt 预算守卫(E1 拒启动)与请求构造 ----------

def _system_messages(system_text: str, user_text: str) -> list[dict]:
    return [{"role": "system", "content": system_text},
            {"role": "user", "content": user_text}]


def check_prompt_fits(config: Config, *, purpose: str = "score") -> None:
    """实例化 system + 最小标题空间 ≥ max_input_tokens → ConfigError(E1
    拒启动;content-editing §3 规则 5);计数不可得同样拒启动。
    purpose ∈ {score, understand}(summarize 复用同一守卫)。"""
    prompt = config.prompts.score if purpose == "score" else config.prompts.understand
    model = config.budget.default_model
    try:
        count = count_request_tokens(
            model, _system_messages(prompt.text, _MIN_USER))
    except TokenizerUnavailable as exc:
        raise ConfigError(
            f"E1.prompt-budget:token 计数不可得,无法验证 prompt 预算({exc})"
        ) from exc
    if count >= config.budget.max_input_tokens:
        raise ConfigError(
            f"E1.prompt-budget:实例化 system({count})+ 最小标题空间 ≥ "
            f"max_input_tokens({config.budget.max_input_tokens}),拒启动")


def build_user_text(title: str, body: str) -> str:
    return f"标题:{title}\n\n正文:\n{body}"


def build_score_ctx(config: Config, member: dict, user_text: str,
                    attempt_tag: str) -> dict:
    """identity_ctx(与 Task 8 复用判定同构同键):attemptTag/正文一字节
    之差均改变 request_hash——截断后实际输入入身份,旧回执不可复用。"""
    ctx = {
        "provider": PROVIDER,
        "endpoint": ENDPOINT,
        "purpose": "score",
        "model": config.budget.default_model,
        "prompt_version": config.prompts.score.version,
        "system_text": config.prompts.score.text,
        "user_text": user_text,
        "max_tokens": config.budget.max_output_tokens,
        "thinking": config.budget.thinking,
        "response_format": "json_object" if config.budget.json_output else "text",
        "identity_key": member["identity_key"],
        "content_hash": member["content_hash"],
        "attemptTag": attempt_tag,
    }
    ctx["request_hash"] = request_hash(ctx)
    return ctx


def _truncate_user(config: Config, title: str, body: str,
                   system_text: str) -> tuple[str, int]:
    """迭代截断正文保标题:二分最大可行前缀 + 固定标记([...truncated]),
    直至完整请求计数 ≤ max_input_tokens;只剩标题仍超 → 标题超界。

    二分按可行性单调假设;tokenizer 并拼下存在极端非单调,此时取到的
    前缀只会更短(保守方向,授权链仍以最终重数为准)。返回 (实际输入,
    最终计数)。TokenizerUnavailable 原样上抛(计数不可得不出网)。
    score/understand 共用(输入侧截断策略与 purpose 无关)。"""
    model = config.budget.default_model
    limit = config.budget.max_input_tokens

    def count_with(prefix_len: int) -> int:
        text = body if prefix_len == len(body) \
            else body[:prefix_len] + _TRUNCATE_MARK
        return count_request_tokens(
            model, _system_messages(system_text, build_user_text(title, text)))

    if count_with(len(body)) <= limit:          # 常见:全文即 fits
        return build_user_text(title, body), count_with(len(body))
    if count_with(0) > limit:
        raise ValueError("title_too_long")       # 只剩标题仍超 → 剔除
    lo, hi = 0, len(body) - 1                    # 全文已不可行,搜最大前缀
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count_with(mid) <= limit:
            lo = mid
        else:
            hi = mid - 1
    user_text = build_user_text(title, body[:lo] + _TRUNCATE_MARK)
    return user_text, count_with(lo)


# ---------- 双次评分主体 ----------

@dataclass(frozen=True)
class _Side:
    score: int | None = None
    receipt_id: int | None = None
    error: str | None = None     # error_class 或 "E4.parse"(received 未过验证器)
    reused: bool = False


def _attempt_side(conn: sqlite3.Connection, config: Config, member: dict,
                  attempt_tag: str, user_text: str, count: int,
                  issue_date: str, transport, now) -> _Side:
    ctx = build_score_ctx(config, member, user_text, attempt_tag)
    logical_key = _logical_key("score", ctx["model"], ctx["request_hash"])

    # 复用/续跑重放(异常 A/B):received/completed 且过完整 E4 → 零网络
    row = conn.execute(
        "SELECT id, status, response_json FROM receipt WHERE logical_key=?",
        (logical_key,)).fetchone()
    if row is not None and row[1] in ("received", "completed") \
            and validate_score_response(row[2]):
        return _Side(score=_score_from_response(row[2]), receipt_id=row[0],
                     reused=True)

    # 重发门(model-calls §3 规则 3):此前发过(同 logical_key 有回执)
    # 的再发送一律过 can_retry 三条件——错误类别/硬上限/unknown 专属等待
    # (≥30min)与名额;首发无回执不经此门。kill 窗口残留的 pending 先
    # 清扫(超窗转 unknown);窗内 pending=在途,等待而非终态。
    origin = "initial"
    if row is not None:
        recover_stale_pending(conn, config, logical_key, now)
        verdict = can_retry(conn, config, logical_key, now)
        if not verdict.allowed:
            if verdict.reason in ("unknown_wait", "attempt_in_flight"):
                return _Side(error="unknown_wait", receipt_id=row[0])
            return _Side(error="no_retry", receipt_id=row[0])
        origin = "retry" if verdict.channel == "normal" else verdict.channel

    ref = authorize(conn, config, purpose="score", model=ctx["model"],
                    request_hash=ctx["request_hash"],
                    identity_key=member["identity_key"], token_count=count,
                    issue_date=issue_date, origin=origin, now=now)
    if ref.status != "reserved":
        return _Side(error=f"gate:{ref.reject_reason}")

    request = LLMRequest(model=ctx["model"],
                         messages=_system_messages(config.prompts.score.text,
                                                   user_text),
                         max_tokens=ctx["max_tokens"], purpose="score",
                         request_hash=ctx["request_hash"])
    try:
        result = call_llm(request, transport=transport)
        error_class, detail = classify_failure(result)
    except Exception as exc:                     # 传输异常 → E3.unknown
        error_class, detail = classify_failure(exc)
        result = None
    if error_class is not None:
        record_failure(conn, config, ref, error_class, detail,
                       usage=getattr(result, "usage", None))
        return _Side(error=error_class)

    record_response(conn, config, ref, result)
    response_json = conn.execute(
        "SELECT response_json FROM receipt WHERE id=?",
        (ref.receipt_id,)).fetchone()[0]
    if not validate_score_response(response_json):
        # HTTP 200+stop+合法 JSON 但业务契约不过(越界/类型/缺字段)→
        # E4.parse(design L211:received→failed,普通有界重试)。usage
        # 已随 record_response 结算;此处单事务把 attempt/receipt 落
        # failed(error_class=retryable——CHECK 三值域,matrix_code 在
        # detail 标 E4.parse),can_retry 普通通道名额内可补发
        record_failure(conn, config, ref, "retryable", {
            "http_status": 200, "matrix_code": "E4.parse",
            "message": (response_json or "")[:200]})
        return _Side(error="E4.parse", receipt_id=ref.receipt_id)
    return _Side(score=_score_from_response(response_json),
                 receipt_id=ref.receipt_id)


def score_entry(conn, config: Config, member: dict, *, issue_date: str,
                transport=None, now: datetime | None = None) -> ScoreOutcome:
    """单成员双次评分入口。拒启/E7/闸门拒为环境性终态(rejected/excluded);
    一侧失败按最重类别返回(retryable/unknown/failed),有效侧 received
    保留供复用(验收 B:部分补全只补缺失侧)。双分齐 → 单事务业务回写。"""
    try:
        user_text, count = _truncate_user(
            config, member["title"], member["content_text"] or "",
            config.prompts.score.text)
    except TokenizerUnavailable:
        return ScoreOutcome("rejected", reason="tokenizer_unavailable")
    except ValueError:
        return ScoreOutcome("excluded", reason="title_too_long")

    sides: list[_Side] = []
    for tag in ScoreTag:
        side = _attempt_side(conn, config, member, tag, user_text, count,
                             issue_date, transport, now)
        if side.error is not None and side.error.startswith("gate:"):
            return ScoreOutcome("rejected", reason=side.error)
        sides.append(side)

    valid = [s for s in sides if s.score is not None]
    if len(valid) == 2:
        analysis_id = _complete_analysis(conn, config, member, sides)
        return ScoreOutcome("completed", score_1=sides[0].score,
                            score_2=sides[1].score, analysis_id=analysis_id,
                            receipt_ids=(sides[0].receipt_id, sides[1].receipt_id))
    errors = [s.error for s in sides if s.score is None]
    outcome = {"no_retry": "failed", "E4.parse": "retryable",
               "retryable": "retryable", "unknown": "unknown",
               "unknown_wait": "unknown"}
    status = "failed" if "no_retry" in errors else next(
        (outcome[e] for e in errors if e in outcome), "failed")
    return ScoreOutcome(status, score_1=sides[0].score, score_2=sides[1].score,
                        receipt_ids=tuple(s.receipt_id for s in valid))


def _complete_analysis(conn, config: Config, member: dict,
                       sides: list[_Side]) -> int:
    """单事务业务回写(规则 8):receipt×2 completed + analysis 行 +
    entry→scored。重放幂等:先查同身份(entry+prompt_version+model)已有
    analysis 行——崩溃在 received 之后本事务之前,续跑复用响应重放本事务。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with conn:
        for side in sides:
            conn.execute(
                "UPDATE receipt SET status='completed', completed_utc=?"
                " WHERE id=? AND status!='completed'", (now, side.receipt_id))
        existing = conn.execute(
            "SELECT id FROM analysis WHERE entry_id=? AND prompt_version=?"
            " AND model=?",
            (member["entry_id"], config.prompts.score.version,
             config.budget.default_model)).fetchone()
        if existing is not None:
            analysis_id = existing[0]
        else:
            cur = conn.execute(
                "INSERT INTO analysis (entry_id, prompt_version, model,"
                " score_1, score_2, selected, receipt_ids, created_utc)"
                " VALUES (?,?,?,?,?,0,?,?)",
                (member["entry_id"], config.prompts.score.version,
                 config.budget.default_model, sides[0].score, sides[1].score,
                 json.dumps([s.receipt_id for s in sides]), now))
            analysis_id = cur.lastrowid
        conn.execute(
            "UPDATE entry SET status='scored' WHERE id=? AND status='pending'",
            (member["entry_id"],))
    return analysis_id
