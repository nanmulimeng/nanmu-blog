# -*- coding: utf-8 -*-
"""ingest(ADR-0012):多 feed 直连轻量采集——TDD 先行测试。
契约:逐 feed 拉取→identity_key 归一判重→entry 落库(全量,预筛统一把关)
→冻结 manifest=discovered 48h 资格条目;单 feed 失败隔离(告警跳过),
全部失败才 E2(CollectError);published 滑出 7 天窗口的条目不入库;幂等=
已冻结直接返回。"""
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nanmu_engine import ingest
from nanmu_engine.collect import CollectError
from nanmu_engine.db import connect_db, migrate

NOW = datetime(2026, 10, 26, 2, 0, 0, tzinfo=timezone.utc)

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>AIHOT</title>
<item>
  <title>条目甲</title>
  <link>https://aihot.news/items/aaa111</link>
  <description><![CDATA[<p>正文甲</p><p>足够长的一段内容,包含足够信息供评分使用。</p>]]></description>
  <pubDate>Sun, 25 Oct 2026 00:00:00 GMT</pubDate>
</item>
<item>
  <title>条目乙</title>
  <link>https://aihot.news/items/bbb222</link>
  <description>纯文本描述乙,无标签。</description>
  <pubDate>Mon, 26 Oct 2026 01:00:00 GMT</pubDate>
</item>
<item>
  <title>坏链接条目</title>
  <link>not a url</link>
  <description>应被 R0 跳过。</description>
</item>
</channel></rss>"""


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    migrate(c)
    return c


def _config(_unused=None):
    from nanmu_engine.config import load_config
    return load_config(Path(__file__).resolve().parents[1])


class TestIngest(unittest.TestCase):
    def test_parse_feed_解析与去标签(self):
        items = ingest._parse_feed(FEED)
        self.assertEqual(len(items), 2, "坏链接(R0 无效)被跳过")
        self.assertEqual(items[0]["title"], "条目甲")
        self.assertEqual(items[0]["url"], "https://aihot.news/items/aaa111")
        self.assertNotIn("<", items[0]["content_text"])
        self.assertIn("正文甲", items[0]["content_text"])
        self.assertEqual(items[0]["published_utc"], "2026-10-25T00:00:00Z")

    def test_ingest_entries_判重与discovered锚定(self):
        c = _conn()
        cfg = _config()
        with mock.patch.object(ingest, "_fetch_feed", return_value=FEED):
            n1 = ingest.ingest_entries(c, NOW, config=cfg, feeds=[("AIHOT", "u")])
            n2 = ingest.ingest_entries(c, NOW + timedelta(hours=1), config=cfg,
                                       feeds=[("AIHOT", "u")])
        self.assertEqual(n1, 2)
        self.assertEqual(n2, 0, "同键二次拉取零新增")
        rows = c.execute(
            "SELECT identity_key, source_name, source_tier, discovered_utc FROM entry").fetchall()
        self.assertEqual(len(rows), 2)
        keys = {r[0] for r in rows}
        self.assertIn("url:https://aihot.news/items/aaa111", keys)
        self.assertTrue(all(r[1] == "AIHOT" for r in rows))
        self.assertTrue(all(r[2] == "T1" for r in rows), "sources.yaml AIHOT→T1")
        self.assertTrue(all(r[3] == NOW.strftime("%Y-%m-%dT%H:%M:%SZ") for r in rows))

    def test_ingest_entries_单feed失败隔离(self):
        c = _conn()
        feeds = [("S1", "https://s1.example/feed"), ("S2", "https://s2.example/feed")]
        with mock.patch.object(ingest, "_fetch_feed",
                               side_effect=[OSError("net down"), FEED]):
            n = ingest.ingest_entries(c, NOW, feeds=feeds)
        self.assertEqual(n, 2, "S1 失败告警跳过,S2 照常落库")

    def test_ingest_entries_全部feed失败_CollectError(self):
        c = _conn()
        with mock.patch.object(ingest, "_fetch_feed", side_effect=OSError("net down")):
            with self.assertRaises(CollectError):
                ingest.ingest_entries(c, NOW,
                                      feeds=[("S1", "u1"), ("S2", "u2")])

    def test_ingest_entries_published过老跳过(self):
        c = _conn()
        stale = FEED.replace("Sun, 25 Oct 2026", "Mon, 05 Oct 2026")  # 21 天前
        with mock.patch.object(ingest, "_fetch_feed", return_value=stale):
            n = ingest.ingest_entries(c, NOW, feeds=[("AIHOT", "u")])
        self.assertEqual(n, 1, "条目甲(05 Oct)滑出 7 天窗口跳过,条目乙新鲜保留")

    def test_ingest_entries_tier从未登记源默认T2(self):
        c = _conn()
        unregistered = FEED.replace("aihot.news/items", "nowhere.example/x")
        with mock.patch.object(ingest, "_fetch_feed", return_value=unregistered):
            ingest.ingest_entries(c, NOW, config=_config(),
                                  feeds=[("陌生源", "u")])
        rows = c.execute("SELECT source_tier FROM entry").fetchall()
        self.assertTrue(all(r[0] == "T2" for r in rows),
                        "sources.yaml 未登记源→unknown_source_tier=T2")

    def test_fetch失败_CollectError(self):
        c = _conn()
        with mock.patch.object(ingest, "_fetch_feed", side_effect=OSError("boom")):
            with self.assertRaises(CollectError):
                ingest.ingest_entries(c, NOW, feeds=[("AIHOT", "u")])

    def test_ingest_once_冻结manifest为48h资格条目且幂等(self):
        import tempfile
        c = _conn()
        with tempfile.TemporaryDirectory() as td:
            cfg = _config()
            with mock.patch.object(ingest, "_fetch_feed", return_value=FEED):
                r1 = ingest.ingest_once(c, cfg, "2026-10-26", NOW)
                self.assertEqual(r1.item_total, 2)
                self.assertFalse(c.in_transaction,
                                 "单次 ingest_once 不得留悬挂事务(collect_once 的"
                                 " BEGIN/COMMIT 包裹语义,freeze_issue 自身不提交;"
                                 "悬挂会炸后续 ledger.authorize 的 BEGIN IMMEDIATE)")
                r2 = ingest.ingest_once(c, cfg, "2026-10-26", NOW + timedelta(hours=1))
        self.assertEqual(r2.item_total, 2, "已冻结幂等返回")
        import json
        m = json.loads(c.execute(
            "SELECT manifest_json FROM issue_freeze WHERE issue_date=?", ("2026-10-26",)).fetchone()[0])
        self.assertEqual(len(m), 2)
        self.assertTrue(all(x["source_name"] == "AIHOT" for x in m))
        import hashlib
        for x in m:  # 与 collect manifest 契约对齐(ledger.reusable_scores 消费)
            self.assertIn("entry_id", x)
            self.assertIn("content_hash", x)
            self.assertEqual(
                x["content_hash"],
                hashlib.sha256(x["content_text"].encode("utf-8")).hexdigest())
        # 旧条目滑出 48h 后不再进 manifest(资格语义)
        c.execute("UPDATE entry SET discovered_utc=?", (
            (NOW - timedelta(hours=49)).strftime("%Y-%m-%dT%H:%M:%SZ"),))
        c.execute("DELETE FROM issue_freeze WHERE issue_date=?", ("2026-10-27",))
        with mock.patch.object(ingest, "_fetch_feed", return_value=FEED):
            r3 = ingest.ingest_once(c, cfg, "2026-10-27", NOW + timedelta(days=1))
        m3 = json.loads(c.execute(
            "SELECT manifest_json FROM issue_freeze WHERE issue_date=?", ("2026-10-27",)).fetchone()[0])
        self.assertEqual(r3.item_total, 0)
        self.assertEqual(len(m3), 0, "资格滑出→空冻结(合法)")

    def test_main_hourly入口(self):
        """timer 入口:--root 解析→加载配置→连库→落库,返回 0。"""
        with mock.patch.object(ingest, "load_config") as lc, \
             mock.patch.object(ingest, "connect_db") as cdb, \
             mock.patch.object(ingest, "ingest_entries", return_value=3) as ie:
            rc = ingest.main(["--root", "/opt/nanmu-blog/engine"])
        self.assertEqual(rc, 0)
        lc.assert_called_once_with(Path("/opt/nanmu-blog/engine"))
        cdb.assert_called_once_with(str(Path("/opt/nanmu-blog/engine") / "engine.db"))
        ie.assert_called_once()
        self.assertEqual(ie.call_args[1].get("config"), lc.return_value)


if __name__ == "__main__":
    unittest.main()
