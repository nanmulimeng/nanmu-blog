"""摘要写作(understand 单次调用;与 score 同构的授权/截断/事务链)。

链路(content-editing §3 规则 2/5/8):构造完整请求→tokenizer 迭代截断
(score 共用策略)→授权→出网→结算→单事务业务回写(receipt completed +
summary 行;entry 状态不动——占用协议属入选判断/发布单元)。

E4 understand 验证器在此定稿并回填 Task 8 桩(ledger._passes_e4
understand 分支)。tags 宽松侧:数组元素非字符串/非数组=E4;数量越界
(>3)截取前 3(§4 非付费错误)。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from nanmu_engine.config import Config
from nanmu_engine.llm import LLMRequest, call_llm, classify_failure
from nanmu_engine.ledger import (
    ENDPOINT,
    PROVIDER,
    _logical_key,
    authorize,
    record_failure,
    record_response,
    request_hash,
)
from nanmu_engine.score import _truncate_user, build_user_text
from nanmu_engine.token_count import TokenizerUnavailable


@dataclass(frozen=True)
class SummaryOutcome:
    status: str                      # completed/retryable/unknown/failed/rejected/excluded
    summary_id: int | None = None
    receipt_ids: tuple[int, ...] = ()
    title_zh: str | None = None
    summary: str | None = None
    reason: str | None = None
    tags: tuple[str, ...] = ()
    fail_reason: str | None = None   # rejected/excluded 原因(gate:*/tokenizer_unavailable/title_too_long)


# ---------- E4 understand 验证器定稿 ----------

def validate_understand_response(response_json: str | None) -> bool:
    """有效性 = finish_reason=stop + content 合法 JSON 对象 + 三字段
    (title_zh/summary/reason)非空字符串 + tags 为字符串数组(数量宽松:
    >3 截取前 3,§4;空列表可通过)。"""
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
    if not all(isinstance(payload.get(k), str) and payload.get(k)
               for k in ("title_zh", "summary", "reason")):
        return False
    tags = payload.get("tags")
    return isinstance(tags, list) and all(isinstance(t, str) for t in tags)


def _payload_of(response_json: str) -> dict:
    return json.loads(json.loads(response_json)["content"])


def _normalize_tags(payload: dict) -> list[str]:
    return [t for t in payload.get("tags", []) if isinstance(t, str)][:3]


# ---------- 请求构造与单次调用 ----------

def _build_ctx(config: Config, member: dict, user_text: str) -> dict:
    ctx = {
        "provider": PROVIDER,
        "endpoint": ENDPOINT,
        "purpose": "understand",
        "model": config.budget.default_model,
        "prompt_version": config.prompts.understand.version,
        "system_text": config.prompts.understand.text,
        "user_text": user_text,
        "max_tokens": config.budget.max_output_tokens,
        "thinking": config.budget.thinking,
        "response_format": "json_object" if config.budget.json_output else "text",
        "identity_key": member["identity_key"],
        "content_hash": member["content_hash"],
        "attemptTag": "understand",
    }
    ctx["request_hash"] = request_hash(ctx)
    return ctx


def understand_entry(conn: sqlite3.Connection, config: Config, member: dict,
                     *, issue_date: str, transport=None,
                     now: datetime | None = None) -> SummaryOutcome:
    """单成员摘要入口。拒启/E7/闸门拒为环境性终态;失败按类别返回
    (retryable/unknown/failed)不写 summary 行(普通项失败隔离:剔除
    该条不挂整期,§3 规则 6)。成功 → 单事务(receipt completed+summary)。"""
    try:
        user_text, count = _truncate_user(
            config, member["title"], member["content_text"] or "",
            config.prompts.understand.text)
    except TokenizerUnavailable:
        return SummaryOutcome("rejected", fail_reason="tokenizer_unavailable")
    except ValueError:
        return SummaryOutcome("excluded", fail_reason="title_too_long")

    ctx = _build_ctx(config, member, user_text)
    logical_key = _logical_key("understand", ctx["model"], ctx["request_hash"])

    # 复用/续跑重放(异常 C):received/completed 且过 E4 → 零网络
    row = conn.execute(
        "SELECT id, status, response_json FROM receipt WHERE logical_key=?",
        (logical_key,)).fetchone()
    if row is not None and row[1] in ("received", "completed") \
            and validate_understand_response(row[2]):
        payload = _payload_of(row[2])
        summary_id = _complete_summary(conn, config, member, row[0], payload)
        return _completed(summary_id, row[0], payload)

    ref = authorize(conn, config, purpose="understand", model=ctx["model"],
                    request_hash=ctx["request_hash"],
                    identity_key=member["identity_key"], token_count=count,
                    issue_date=issue_date, origin="initial", now=now)
    if ref.status != "reserved":
        return SummaryOutcome("rejected", fail_reason=f"gate:{ref.reject_reason}")

    request = LLMRequest(model=ctx["model"],
                         messages=[{"role": "system",
                                    "content": ctx["system_text"]},
                                   {"role": "user", "content": user_text}],
                         max_tokens=ctx["max_tokens"], purpose="understand",
                         request_hash=ctx["request_hash"])
    try:
        result = call_llm(request, transport=transport)
        error_class, detail = classify_failure(result)
    except Exception as exc:
        error_class, detail = classify_failure(exc)
        result = None
    if error_class is not None:
        record_failure(conn, config, ref, error_class, detail,
                       usage=getattr(result, "usage", None))
        return SummaryOutcome(error_class if error_class != "no_retry"
                              else "failed", fail_reason=error_class)

    record_response(conn, config, ref, result)
    response_json = conn.execute(
        "SELECT response_json FROM receipt WHERE id=?",
        (ref.receipt_id,)).fetchone()[0]
    if not validate_understand_response(response_json):
        return SummaryOutcome("retryable", fail_reason="E4.parse")
    payload = _payload_of(response_json)
    summary_id = _complete_summary(conn, config, member, ref.receipt_id, payload)
    return _completed(summary_id, ref.receipt_id, payload)


def _completed(summary_id: int, receipt_id: int, payload: dict) -> SummaryOutcome:
    return SummaryOutcome("completed", summary_id=summary_id,
                          receipt_ids=(receipt_id,),
                          title_zh=payload["title_zh"],
                          summary=payload["summary"],
                          reason=payload["reason"],
                          tags=tuple(_normalize_tags(payload)))


def _complete_summary(conn: sqlite3.Connection, config: Config, member: dict,
                      receipt_id: int, payload: dict) -> int:
    """单事务业务回写(规则 8):receipt completed + summary 行。重放幂等:
    先查同身份(entry+prompt_version+model)已有行。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with conn:
        conn.execute(
            "UPDATE receipt SET status='completed', completed_utc=?"
            " WHERE id=? AND status!='completed'", (now, receipt_id))
        existing = conn.execute(
            "SELECT id FROM summary WHERE entry_id=? AND prompt_version=?"
            " AND model=?",
            (member["entry_id"], config.prompts.understand.version,
             config.budget.default_model)).fetchone()
        if existing is not None:
            return existing[0]
        cur = conn.execute(
            "INSERT INTO summary (entry_id, prompt_version, model, title_zh,"
            " summary, reason, tags_json, receipt_ids, created_utc)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (member["entry_id"], config.prompts.understand.version,
             config.budget.default_model, payload["title_zh"],
             payload["summary"], payload["reason"],
             json.dumps(_normalize_tags(payload), ensure_ascii=False),
             json.dumps([receipt_id]), now))
        return cur.lastrowid
