"""通知去重与发送(notify_sent 同 key UPSERT;scheduling-ops §3 规则 7)。

dedup_key=错误子类+":"+issue_date(事件类);warn-monthly:YYYY-M(月度);
配置错误类附配置 hash(变更后新键)。写法=同 key UPSERT:首现 INSERT、
重试成功 UPDATE result/sent_utc——dedup_key 是主键,同 key 二次 INSERT
必然冲突,不得另起一行。"立即通知"=发送时机(E1/402/E8/E9/W1 发生即发,
不等聚合),不是每次重跑都重发;连续 2 期类(E2/E6/无合格)按子类+期判
二期后发送。发送失败有界重试,不改账本与旧站。

崩溃边界(承诺收窄):发送成功但结果未持久化即崩溃→重启可能重复通知;
UPSERT 只约束已落库记录。不承诺外部 exactly-once,也不承诺至多一次。
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Callable

logger = logging.getLogger(__name__)

Sender = Callable[[str, str], str]

_IMMEDIATE_PREFIXES = ("E1", "402", "E8", "E9", "W1", "auto_expire")
_TWO_PERIOD_PREFIXES = ("E2", "E6", "zero_qualified", "no_candidates")


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def notify(conn: sqlite3.Connection, dedup_key: str, message: str, *,
           send: Sender, retries: int = 3, channel: str = "log") -> str:
    """单事件通知:已落库且成功→零重发;否则发送(有界重试)→同 key
    UPSERT 落库(首现 INSERT/重试 UPDATE 原行)。返回 sent/deduped/failed。"""
    row = conn.execute(
        "SELECT result FROM notify_sent WHERE dedup_key=?",
        (dedup_key,)).fetchone()
    if row is not None and row[0] == "sent":
        return "deduped"

    result = "failed"
    for attempt in range(max(1, retries)):
        try:
            result = str(send(dedup_key, message))
            break
        except Exception as exc:            # 有界重试;失败不另起行不改账本
            logger.warning("stage=notify event=send_failed key=%s"
                           " attempt=%d message=%s", dedup_key, attempt + 1,
                           exc)
    with conn:
        conn.execute(
            "INSERT INTO notify_sent (dedup_key, channel, sent_utc, result)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(dedup_key) DO UPDATE SET"
            " channel=excluded.channel, sent_utc=excluded.sent_utc,"
            " result=excluded.result",
            (dedup_key, channel, _utc_now(), result))
    return result if result != "deduped" else "sent"


def notify_event(conn: sqlite3.Connection, subclass: str, issue_date: str,
                 message: str, *, send: Sender, key_extra: str | None = None,
                 retries: int = 3) -> str:
    """事件类入口。立即类(E1/402/E8/E9/W1/到期移出清单)发生即发;连续
    2 期类(E2/E6/无合格)按子类判二期——该子类曾在他期失败(digest_issue
    failed 同前缀)才发送,首期不发送不落表。其余未知子类保守发送。
    配置错误类经 key_extra 附配置 hash(变更后新键)。"""
    if subclass.startswith(_TWO_PERIOD_PREFIXES) \
            and not subclass.startswith(_IMMEDIATE_PREFIXES):
        prev = conn.execute(
            "SELECT 1 FROM digest_issue WHERE status='failed'"
            " AND fail_reason LIKE ? || '%' AND issue_date < ? LIMIT 1",
            (subclass, issue_date)).fetchone()
        if prev is None:
            return "suppressed_first"       # 首期:不发送不落表
    dedup_key = f"{subclass}:{issue_date}"
    if key_extra:
        dedup_key = f"{dedup_key}:{key_extra}"
    return notify(conn, dedup_key, message, send=send, retries=retries)


def notify_monthly(conn: sqlite3.Connection, month: str, message: str, *,
                   send: Sender, retries: int = 3) -> str:
    """月度预警(¥40):warn-monthly:YYYY-M,同月一封。"""
    return notify(conn, f"warn-monthly:{month}", message, send=send,
                  retries=retries)
