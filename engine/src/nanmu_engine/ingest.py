"""ingest(ADR-0012):多 feed 直连轻量采集。

契约:逐 feed 拉取 → identity_key 归一判重 → entry 落库(全量,预筛统一
把关正文质量)→ 冻结 manifest=discovered 48h 资格条目。单 feed 失败
隔离(告警跳过,其余源继续);全部 feed 失败才 E2(CollectError,与
collect 同语义);published 滑出 7 天窗口的条目不入库(防全量历史 feed
污染资格池)。幂等=已冻结直接返回既有结果。不部署常驻进程:hourly
timer 调 ingest_entries(只落库),每日 run 调 ingest_once(落库+冻结)。
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from .collect import CollectError, CollectResult, freeze_issue
from .normalize import identity_key

logger = logging.getLogger(__name__)

# 多 feed 清单(ADR-0012,2026-10-26 服务器实测可达;tier 真相源=sources.yaml)
FEEDS: tuple[tuple[str, str], ...] = (
    ("AIHOT", "https://aihot.news/feed.xml"),
    ("Techmeme", "https://www.techmeme.com/feed.xml"),
    ("MarkTechPost", "https://www.marktechpost.com/feed/"),
    ("Hacker News", "https://hnrss.org/frontpage?points=100"),
    ("MIT Tech Review AI",
     "https://www.technologyreview.com/topic/artificial-intelligence/feed/"),
)
DEFAULT_FEED_URL = FEEDS[0][1]     # 兼容单 feed 环境变量覆盖(NANMU_INGEST_FEED_URL)
DEFAULT_SOURCE_NAME = "AIHOT"
DEFAULT_TIER = "T1"           # ADR-0012:高编辑质量聚合(与 sources.yaml 同步)
_ELIGIBILITY_WINDOW_H = 48    # 候选资格窗口(与 collect 双层窗口语义一致)
_STALE_PUBLISHED_H = 24 * 7   # published 新鲜度上限(防全量历史 feed 灌库)
_TAG_RE = re.compile(r"<[^>]+>")


def _fetch_feed(url: str | None = None, timeout: float = 30.0) -> str:
    """拉 feed 文本;任何传输层失败=CollectError(E2)。"""
    target = url or os.environ.get("NANMU_INGEST_FEED_URL", DEFAULT_FEED_URL)
    try:
        resp = httpx.get(target, timeout=timeout, follow_redirects=True,
                         headers={"User-Agent": "nanmu-blog-engine/1.0"})
        resp.raise_for_status()
        return resp.text
    except Exception as exc:  # noqa: BLE001 统一转 E2 语义
        raise CollectError(f"ingest feed 拉取失败({target}):{exc}") from exc


def _strip_tags(html: str) -> str:
    text = _TAG_RE.sub(" ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_feed(xml_text: str) -> list[dict]:
    """item → {identity_key,url,title,published_utc,content_text};无效链接跳过。"""
    out = []
    for item in ET.fromstring(xml_text).iter("item"):
        link = (item.findtext("link") or "").strip()
        key = identity_key(link)
        if key is None:
            logger.warning("stage=ingest event=candidate_invalid url=%r", link[:80])
            continue
        pub = item.findtext("pubDate")
        published = None
        if pub:
            try:
                published = _iso_z(parsedate_to_datetime(pub.strip()))
            except (TypeError, ValueError):
                published = None
        out.append({
            "identity_key": key,
            "url": link,
            "title": (item.findtext("title") or "").strip(),
            "published_utc": published,
            "content_text": _strip_tags(item.findtext("description") or ""),
        })
    return out


def ingest_entries(engine_conn: sqlite3.Connection, now_utc: datetime,
                   *, config=None,
                   feeds: tuple[tuple[str, str], ...] | None = None) -> int:
    """逐 feed 拉取+判重落库;返回新增条数(同键零新增)。

    单 feed 失败=告警跳过(其余源继续);全部失败=CollectError(E2)。
    tier 查 sources.yaml(未登记源用 unknown_source_tier,告警留痕)。
    """
    feed_list = FEEDS if feeds is None else feeds
    tier_map: dict[str, str] = {}
    unknown_tier = DEFAULT_TIER if config is None else config.sources.unknown_source_tier
    if config is not None:
        tier_map = {s.name: s.tier for s in config.sources.sources}
    stale_cutoff = _iso_z(now_utc - timedelta(hours=_STALE_PUBLISHED_H))
    first_seen = _iso_z(now_utc)
    total_added = 0
    failed = 0
    for source_name, url in feed_list:
        try:
            items = _parse_feed(_fetch_feed(url))
        except CollectError as exc:
            failed += 1
            logger.warning("stage=ingest event=feed_failed source=%s err=%s",
                           source_name, exc)
            continue
        except Exception as exc:  # noqa: BLE102 传输/解析层异常统一计数
            failed += 1
            logger.warning("stage=ingest event=feed_failed source=%s err=%s",
                           source_name, exc)
            continue
        tier = tier_map.get(source_name)
        if tier is None:
            logger.warning("stage=ingest event=source_unregistered source=%s"
                           " tier=%s", source_name, unknown_tier)
            tier = unknown_tier
        eligible = [it for it in items
                    if it["published_utc"] is None
                    or it["published_utc"] >= stale_cutoff]
        added = 0
        for it in eligible:
            cur = engine_conn.execute(
                "INSERT OR IGNORE INTO entry (identity_key, url, title,"
                " source_name, source_tier, published_utc,"
                " discovered_utc, content_text)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (it["identity_key"], it["url"], it["title"], source_name,
                 tier, it["published_utc"], first_seen, it["content_text"]))
            added += cur.rowcount
        engine_conn.commit()
        logger.info("stage=ingest event=entries source=%s fetched=%d"
                    " eligible=%d added=%d", source_name, len(items),
                    len(eligible), added)
        total_added += added
    if feed_list and failed == len(feed_list):
        raise CollectError(f"ingest 全部 {failed} 个 feed 拉取失败")
    return total_added


def _eligible_manifest(engine_conn: sqlite3.Connection,
                       now_utc: datetime) -> list[dict]:
    """冻结候选=discovered 48h 资格窗口内全部 entry(used 除外,预筛再分层)。"""
    since = _iso_z(now_utc - timedelta(hours=_ELIGIBILITY_WINDOW_H))
    rows = engine_conn.execute(
        "SELECT identity_key, url, title, source_name, source_tier,"
        " published_utc, discovered_utc, content_text FROM entry"
        " WHERE discovered_utc >= ? AND status != 'used'"
        " ORDER BY discovered_utc DESC, identity_key",
        (since,)).fetchall()
    keys = ["identity_key", "url", "title", "source_name", "source_tier",
            "published_utc", "discovered_utc", "content_text"]
    return [dict(zip(keys, r)) for r in rows]


def ingest_once(engine_conn: sqlite3.Connection, config, issue_date: str,
                now_utc: datetime) -> CollectResult:
    """每日 run 入口:落库 → 冻结资格 manifest;已冻结幂等返回。"""
    ingest_entries(engine_conn, now_utc, config=config)
    manifest = _eligible_manifest(engine_conn, now_utc)
    frozen_utc = freeze_issue(engine_conn, issue_date, manifest, now_utc)
    status = "frozen" if frozen_utc == _iso_z(now_utc) else "already_frozen"
    return CollectResult(status=status, manifest=manifest,
                         item_total=len(manifest))
