"""collect 只读采集与 entry 落库测试(种子=data-ingestion 验收 1/5/6/7/12/13;
夹具=临时 SQLite 模拟 topic-digest 库,schema 逐字 data-source 契约)。"""

import dataclasses
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import nanmu_engine.collect as collect_mod
from nanmu_engine.collect import CollectError, collect_once
from nanmu_engine.config import (SourceEntry, SourcesConfig, load_config)
from nanmu_engine.db import connect_db, migrate

ENGINE_ROOT = Path(__file__).resolve().parents[1]

T0 = datetime(2026, 10, 6, 8, 30, tzinfo=timezone.utc)


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


_UPSTREAM_DDL = """
CREATE TABLE item(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER NOT NULL REFERENCES source(id),
  url_hash TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  published_utc TEXT,
  fetched_utc TEXT NOT NULL,
  content_text TEXT,
  status TEXT NOT NULL DEFAULT 'fresh'
    CHECK(status IN ('fresh','clustered','dropped'))
);
CREATE TABLE source(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id INTEGER NOT NULL,
  feed_url TEXT NOT NULL UNIQUE,
  name TEXT,
  kind TEXT NOT NULL DEFAULT 'rss',
  weight REAL NOT NULL DEFAULT 1.0,
  enabled INTEGER NOT NULL DEFAULT 1,
  etag TEXT, last_modified TEXT, last_success_at TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  latest_item_published_at TEXT, notes TEXT
);
"""


def _make_upstream(tmp_path):
    path = tmp_path / "topic-digest.db"
    conn = sqlite3.connect(path)
    conn.executescript(_UPSTREAM_DDL)
    conn.commit()
    return conn, str(path)


def _add_source(conn, name, *, enabled=1):
    cur = conn.execute(
        "INSERT INTO source (topic_id, feed_url, name, enabled)"
        " VALUES (1, ?, ?, ?)", (f"https://feed/{name}", name, enabled))
    conn.commit()
    return cur.lastrowid


def _add_item(conn, source_id, url, title, *, fetched, content=None,
              status="clustered", published=None):
    cur = conn.execute(
        "INSERT INTO item (source_id, url_hash, url, title, published_utc,"
        " fetched_utc, content_text, status) VALUES (?,?,?,?,?,?,?,?)",
        (source_id, hashlib.sha256(url.encode()).hexdigest(), url, title,
         published, _fmt(fetched), content, status))
    conn.commit()
    return cur.lastrowid


def _cfg(config, entries, excludes=()):
    return dataclasses.replace(
        config,
        sources=SourcesConfig(1, "T2", tuple(entries), tuple(excludes)))


@pytest.fixture
def env(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    config = load_config(ENGINE_ROOT)
    return conn, config, tmp_path


def _run(conn, upstream_path, config, issue_date, now):
    return collect_once(conn, upstream_path, config, issue_date, now)


# ---------- 验收 1:多源同 key 平局(选择依据在日志) ----------

def test_multisource_same_key_picks_t1(env, caplog):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    # 同键 URL 变体(www 前缀差异),url_hash 不同不撞 UNIQUE
    sid_a = _add_source(up, "src-a")
    sid_b = _add_source(up, "src-b")
    _add_item(up, sid_a, "https://example.com/x", "title-A",
              fetched=T0 - timedelta(hours=1), content="from-A")
    _add_item(up, sid_b, "https://www.example.com/x/", "title-B",
              fetched=T0 - timedelta(minutes=50), content="from-B")
    cfg = _cfg(config, [SourceEntry("src-a", "T1", 100),
                        SourceEntry("src-b", "T2", 50)])
    with caplog.at_level("INFO", logger="nanmu_engine.collect"):
        result = _run(conn, path, cfg, "2026-10-06", T0)
    assert result.status == "frozen"
    assert len(result.manifest) == 1
    member = result.manifest[0]
    assert member["source_tier"] == "T1" and member["source_name"] == "src-a"
    assert member["content_text"] == "from-A"       # T1 胜出(tier 压过 priority)
    # discovered_utc 初值=同键行最早 fetched(两行中 1h 前更早)
    assert member["discovered_utc"] == _fmt(T0 - timedelta(hours=1))
    # 选择依据写日志
    assert any("merge_winner" in r.message and "src-a" in r.message
               for r in caplog.records)


# ---------- 验收 5:快照刷新(新期新 hash、旧期 manifest 不变) ----------

def test_snapshot_refresh_new_issue_new_hash(env):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, "src-a")
    _add_item(up, sid, "https://example.com/x", "t1",
              fetched=T0 - timedelta(hours=1), content=None)  # 正文空
    cfg = _cfg(config, [SourceEntry("src-a", "T1", 100)])
    r1 = _run(conn, path, cfg, "2026-10-06", T0)
    old_hash = r1.manifest[0]["content_hash"]
    assert r1.manifest[0]["content_text"] is None

    # 上游重抓:同 item 行正文空→非空;下一期采集
    up.execute("UPDATE item SET content_text='new body', title='t1-v2'"
               " WHERE source_id=?", (sid,))
    up.commit()
    now2 = T0 + timedelta(hours=26)
    r2 = _run(conn, path, cfg, "2026-10-07", now2)
    new_hash = r2.manifest[0]["content_hash"]
    assert new_hash == hashlib.sha256(b"new body").hexdigest()
    assert new_hash != old_hash
    # 旧期 manifest 不变(续跑请求身份=旧 hash)
    row = conn.execute("SELECT manifest_json FROM issue_freeze"
                       " WHERE issue_date='2026-10-06'").fetchone()
    assert json.loads(row[0])[0]["content_hash"] == old_hash
    # entry 台账已更新
    entry = conn.execute("SELECT content_text, title FROM entry").fetchone()
    assert entry == ("new body", "t1-v2")


# ---------- 验收 6:used 不刷新 ----------

def test_used_entry_not_refreshed(env):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, "src-a")
    _add_item(up, sid, "https://example.com/x", "t1",
              fetched=T0 - timedelta(hours=1), content="v1")
    cfg = _cfg(config, [SourceEntry("src-a", "T1", 100)])
    _run(conn, path, cfg, "2026-10-06", T0)
    conn.execute("UPDATE entry SET status='used'")
    conn.commit()

    up.execute("UPDATE item SET content_text='v2' WHERE source_id=?", (sid,))
    up.commit()
    r2 = _run(conn, path, cfg, "2026-10-07", T0 + timedelta(hours=26))
    entry = conn.execute("SELECT content_text FROM entry").fetchone()
    assert entry[0] == "v1"                      # 台账不动
    assert r2.manifest[0]["content_text"] == "v1"  # manifest 也不反映新正文
    assert r2.manifest[0]["content_hash"] == hashlib.sha256(b"v1").hexdigest()


# ---------- 验收 7:双层窗口与寿命锚定 ----------

def test_lifetime_anchor_discovered_immutable_and_expiry(env, caplog):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, "src-a")
    _add_item(up, sid, "https://example.com/x", "t1",
              fetched=T0 - timedelta(hours=1), content="v1")
    cfg = _cfg(config, [SourceEntry("src-a", "T1", 100)])
    _run(conn, path, cfg, "2026-10-06", T0)
    fixed = _fmt(T0 - timedelta(hours=1))

    # 两天后:同身份经 URL 变体再进上游窗口(fetched 新)——正文照常刷新,
    # 但 discovered_utc 固定,且距冻结时刻超 48h → 不进新期 manifest
    _add_item(up, sid, "https://example.com/x?utm_source=revive", "t1",
              fetched=T0 + timedelta(hours=47), content="v2")
    now3 = T0 + timedelta(hours=49, minutes=30)
    with caplog.at_level("INFO", logger="nanmu_engine.collect"):
        r3 = _run(conn, path, cfg, "2026-10-08", now3)
    assert r3.manifest == []                       # candidate_expired 排除
    assert any("candidate_expired" in r.message for r in caplog.records)
    entry = conn.execute(
        "SELECT discovered_utc, content_text FROM entry").fetchone()
    assert entry[0] == fixed                       # 寿命锚点不变
    assert entry[1] == "v2"                        # 台账正文照常刷新
    # 已冻结旧期 manifest 完好
    row = conn.execute("SELECT entry_count FROM issue_freeze"
                       " WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == 1


def test_new_key_multirow_discovered_is_earliest_fetch(env):
    # 新键同轮两行:胜出按 tier,discovered=最早 fetched(两者独立)
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid_a = _add_source(up, "src-a")
    sid_b = _add_source(up, "src-b")
    _add_item(up, sid_a, "https://example.com/x", "A",
              fetched=T0 - timedelta(minutes=20), content="from-A")
    _add_item(up, sid_b, "https://www.example.com/x", "B",
              fetched=T0 - timedelta(minutes=60), content="from-B")
    cfg = _cfg(config, [SourceEntry("src-a", "T1", 100),
                        SourceEntry("src-b", "T2", 100)])
    r = _run(conn, path, cfg, "2026-10-06", T0)
    assert r.manifest[0]["source_name"] == "src-a"           # tier 胜出
    assert r.manifest[0]["discovered_utc"] == _fmt(
        T0 - timedelta(minutes=60))                           # 最早 fetched


# ---------- 未登记源 ----------

def test_unregistered_source_defaults_t2_with_warning(env, caplog):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, None)      # source.name 为空
    _add_item(up, sid, "https://example.com/x", "t1",
              fetched=T0 - timedelta(hours=1), content="c")
    with caplog.at_level("WARNING", logger="nanmu_engine.collect"):
        r = _run(conn, path, config, "2026-10-06", T0)   # 未登记 → T2
    assert r.manifest[0]["source_tier"] == "T2"
    assert any("unknown_source" in r.message for r in caplog.records)


# ---------- 验收 3:幂等入口(上游查询 0 次) ----------

def test_idempotent_second_collect_never_touches_upstream(env):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, "src-a")
    _add_item(up, sid, "https://example.com/x", "t1",
              fetched=T0 - timedelta(hours=1), content="c")
    cfg = _cfg(config, [SourceEntry("src-a", "T1", 100)])
    r1 = _run(conn, path, cfg, "2026-10-06", T0)
    # 第二次传不存在的路径:若试图连上游会 E2——already_frozen 不碰上游
    r2 = _run(conn, str(tmp_path / "missing.db"), cfg, "2026-10-06", T0)
    assert r2.status == "already_frozen"
    assert r2.manifest == r1.manifest


# ---------- 验收 2:冻结原子性(单事务回滚) ----------

def test_freeze_atomicity_rollback_on_interrupt(env):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, "src-a")
    _add_item(up, sid, "https://example.com/x", "t1",
              fetched=T0 - timedelta(hours=1), content="c")
    cfg = _cfg(config, [SourceEntry("src-a", "T1", 100)])
    conn.execute(
        "CREATE TRIGGER boom BEFORE INSERT ON issue_freeze"
        " BEGIN SELECT RAISE(ABORT, 'boom'); END")
    conn.commit()
    with pytest.raises(sqlite3.DatabaseError):
        _run(conn, path, cfg, "2026-10-06", T0)
    assert conn.execute("SELECT COUNT(*) FROM issue_freeze").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 0  # 无半写


# ---------- 验收 12:E2 上游拒绝只读 ----------

def test_e2_upstream_unreadable(env, caplog):
    conn, config, tmp_path = env
    with caplog.at_level("ERROR", logger="nanmu_engine.collect"):
        with pytest.raises(CollectError):
            _run(conn, str(tmp_path / "missing.db"), config,
                 "2026-10-06", T0)
    assert any("collect_failed" in r.message and "E2" in r.message
               for r in caplog.records)
    assert conn.execute("SELECT COUNT(*) FROM issue_freeze").fetchone()[0] == 0


# ---------- 验收 13:规模护栏 ----------

def test_scale_guard_warning(env, tmp_path, monkeypatch, caplog):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, "src-a")
    for i in range(4):
        _add_item(up, sid, f"https://example.com/x{i}", f"t{i}",
                  fetched=T0 - timedelta(hours=1), content="c")
    monkeypatch.setattr(collect_mod, "_SCALE_ITEMS_WARN", 3)
    with caplog.at_level("WARNING", logger="nanmu_engine.collect"):
        _run(conn, path, _cfg(config, [SourceEntry("src-a", "T1", 100)]),
             "2026-10-06", T0)
    assert any("scale_guard" in r.message for r in caplog.records)


# ---------- 采集语义细节 ----------

def test_window_filters_status_enabled_and_dropped(env):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid_on = _add_source(up, "src-a")
    sid_off = _add_source(up, "src-off", enabled=0)
    _add_item(up, sid_on, "https://example.com/keep", "k",
              fetched=T0 - timedelta(hours=1), content="c", status="fresh")
    _add_item(up, sid_on, "https://example.com/drop", "d",
              fetched=T0 - timedelta(hours=1), content="c", status="dropped")
    _add_item(up, sid_off, "https://example.com/off", "o",
              fetched=T0 - timedelta(hours=1), content="c")
    _add_item(up, sid_on, "https://example.com/old", "old",
              fetched=T0 - timedelta(hours=49), content="c")  # 出 48h 窗
    r = _run(conn, path, _cfg(config, [SourceEntry("src-a", "T1", 100)]),
             "2026-10-06", T0)
    keys = {m["identity_key"] for m in r.manifest}
    assert keys == {"url:https://example.com/keep"}


def test_r0_invalid_url_skipped_with_log(env, caplog):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, "src-a")
    _add_item(up, sid, "ftp://example.com/x", "bad",
              fetched=T0 - timedelta(hours=1), content="c")
    with caplog.at_level("INFO", logger="nanmu_engine.collect"):
        r = _run(conn, path, _cfg(config, [SourceEntry("src-a", "T1", 100)]),
                 "2026-10-06", T0)
    assert r.manifest == []
    assert any("invalid_url" in r.message for r in caplog.records)
