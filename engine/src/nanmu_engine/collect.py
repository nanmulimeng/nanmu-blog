"""只读采集与 entry 落库(data-ingestion §5 写入协议步骤 1-4)。

上游 topic-digest SQLite 只读(mode=ro,不加索引不改 schema);窗口=
fetched_utc 近 48h JOIN data-source 契约;本地 entry upsert + 候选资格
过滤 + issue_freeze 冻结在**同一写事务**提交(崩溃=无冻结行,重跑无损)。
预筛(步骤 5)是纯函数,属后续模块;本模块止于冻结。
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nanmu_engine.config import Config
from nanmu_engine.db import connect_readonly
from nanmu_engine.normalize import identity_key

logger = logging.getLogger(__name__)

_SCALE_ITEMS_WARN = 50_000     # design.md collect 契约规模护栏
_SCALE_QUERY_MS_WARN = 1_000

_WINDOW_HOURS = 48
_TIER_RANK = {"T1": 0, "T2": 1}
_UNREGISTERED_PRIORITY = 100   # sources.yaml priority 默认值

_WINDOW_SQL = (
    "SELECT i.id, i.url, i.title, i.published_utc, i.fetched_utc,"
    " i.content_text, s.name"
    " FROM item i JOIN source s ON i.source_id = s.id"
    " WHERE s.enabled = 1 AND i.status IN ('fresh','clustered')"
    " AND i.fetched_utc >= ?"
    " ORDER BY i.id"
)


class CollectError(Exception):
    """E2:上游读取失败(打不开/权限/schema 依赖红)。

    digest_issue failed 行由单元五按该分类落库;本模块以日志为最小证据。
    """


@dataclass
class CollectResult:
    status: str                  # 'frozen' | 'already_frozen'
    manifest: list = field(default_factory=list)
    item_total: int = 0
    query_ms: int = 0
    warnings: list = field(default_factory=list)


def _source_map(config: Config) -> dict:
    """sources.yaml 名单:name → (tier, priority)。"""
    return {entry.name: (entry.tier, entry.priority)
            for entry in config.sources.sources}


def _parse_utc(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def collect_once(engine_conn: sqlite3.Connection, upstream_path: str,
                 config: Config, issue_date: str,
                 now_utc: datetime) -> CollectResult:
    """采集→判重合并→entry 落库→冻结(单事务);幂等入口=已冻结直接返回。

    R0 invalid 与上游异常格式 fetched_utc 跳过记日志;多源同 key 平局
    tier→priority→name→item.id 升序,选择依据写日志;新键 discovered_utc=
    本轮同键行最早 fetched_utc,已存在键沿用固定值(寿命锚定)。
    """
    frozen = engine_conn.execute(
        "SELECT manifest_json FROM issue_freeze WHERE issue_date=?",
        (issue_date,)).fetchone()
    if frozen is not None:
        return CollectResult("already_frozen",
                             manifest=json.loads(frozen[0]))

    # 1) 只读窗口查询(规模护栏:行数与耗时)
    try:
        upstream = connect_readonly(upstream_path)
        cutoff = (now_utc - timedelta(hours=_WINDOW_HOURS)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        started = time.perf_counter()
        rows = upstream.execute(_WINDOW_SQL, (cutoff,)).fetchall()
        query_ms = int((time.perf_counter() - started) * 1000)
        upstream.close()
    except sqlite3.Error as exc:
        logger.error("stage=collect event=collect_failed error_class=E2"
                     " upstream=%s message=%s", upstream_path, exc)
        raise CollectError(f"E2 上游读取失败:{exc}") from exc
    if len(rows) > _SCALE_ITEMS_WARN or query_ms > _SCALE_QUERY_MS_WARN:
        logger.warning("stage=collect event=scale_guard item_total=%d"
                       " query_ms=%d", len(rows), query_ms)

    # 2) 归一与内存合并(胜出行与 discovered_utc 初值相互独立)
    known = _source_map(config)
    unknown_tier = config.sources.unknown_source_tier
    groups: dict[str, list] = {}
    for item_id, url, title, published, fetched, content, source_name in rows:
        key = identity_key(url)
        if key is None:
            logger.info("stage=collect event=invalid_url url=%r item_id=%s",
                        url, item_id)
            continue
        if source_name not in known:      # 未登记或 name 空均记 warning
            logger.warning("stage=collect event=unknown_source name=%r"
                           " tier=%s", source_name, unknown_tier)
        tier, priority = known.get(source_name or "",
                                   (unknown_tier, _UNREGISTERED_PRIORITY))
        groups.setdefault(key, []).append(
            (item_id, url, title or "", published, fetched, content,
             source_name or "", tier, priority))

    members: list[dict] = []
    now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        engine_conn.execute("BEGIN IMMEDIATE")
        for key, group in groups.items():
            # 平局链:tier(T1 优先)→ priority(小者优)→ name 字典序 →
            # item.id 升序(最小者胜,最终平局键;输入行序无关)
            item_id, url, title, published, fetched, content, \
                source_name, tier, priority = min(
                    group, key=lambda r: (_TIER_RANK.get(r[7], 1), r[8],
                                          r[6], r[0]))
            if len(group) > 1:
                logger.info("stage=collect event=merge_winner key=%s"
                            " source=%s tier=%s item_id=%s rows=%d",
                            key, source_name, tier, item_id, len(group))
            first_seen = min(r[4] for r in group)   # 新键寿命初值=最早 fetched

            # entry upsert:新键 INSERT;已有键未 used 且正文变化 → UPDATE
            existing = engine_conn.execute(
                "SELECT id, status, content_text, discovered_utc"
                " FROM entry WHERE identity_key=?", (key,)).fetchone()
            if existing is None:
                cur = engine_conn.execute(
                    "INSERT INTO entry (identity_key, url, title,"
                    " source_name, source_tier, published_utc,"
                    " discovered_utc, content_text)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (key, url, title, source_name, tier, published,
                     first_seen, content))
                entry_id, discovered = cur.lastrowid, first_seen
            else:
                entry_id, status, old_text, discovered = existing
                if status != "used" and (old_text or "") != (content or ""):
                    engine_conn.execute(
                        "UPDATE entry SET content_text=?, title=? WHERE id=?",
                        (content, title, entry_id))
            # 台账终值即 manifest 快照源(used 不刷新 → 用旧值)
            row = engine_conn.execute(
                "SELECT content_text, title FROM entry WHERE id=?",
                (entry_id,)).fetchone()

            # 候选资格:discovered_utc 距冻结时刻不足 48h 才进 manifest
            anchor = _parse_utc(discovered)
            if anchor is None or now_utc - anchor >= timedelta(
                    hours=_WINDOW_HOURS):
                logger.info("stage=collect event=candidate_expired key=%s"
                            " discovered_utc=%s", key, discovered)
                continue
            members.append({
                "identity_key": key, "entry_id": entry_id, "url": url,
                "title": row[1], "source_name": source_name,
                "source_tier": tier, "published_utc": published,
                "discovered_utc": discovered, "content_text": row[0],
                "content_hash": hashlib.sha256(
                    (row[0] or "").encode("utf-8")).hexdigest(),
            })

        engine_conn.execute(
            "INSERT INTO issue_freeze (issue_date, frozen_utc, entry_count,"
            " manifest_json) VALUES (?,?,?,?)",
            (issue_date, now_iso, len(members),
             json.dumps(members, ensure_ascii=False)))
        engine_conn.execute("COMMIT")       # 冻结确认事件在此刻发生
    except Exception:
        try:
            engine_conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return CollectResult("frozen", manifest=members, item_total=len(rows),
                         query_ms=query_ms)
