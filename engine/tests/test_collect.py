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


# ---------- 审计修正(2026-10-07):ro 直读 readonly 失败的权限缺口诊断 ----------

def test_e2_readonly_error_reports_permission_gap(env, monkeypatch, caplog):
    """审计修正①:快照方案撤回(裸拷+quick_check 不构成一致性保证,
    WAL 内已提交数据亦漏)。nanmu 无上游 data/ 的 -shm 写权时 ro 直读
    报 readonly——E2 信息须带最小权限缺口说明(供用户裁决),引擎
    不擅改上游、不降级读取。"""
    conn, config, tmp_path = env

    def fake_ro(path, *, immutable=False):
        raise sqlite3.OperationalError(
            "attempt to write a readonly database")

    monkeypatch.setattr(collect_mod, "connect_readonly", fake_ro)
    with caplog.at_level("ERROR", logger="nanmu_engine.collect"):
        with pytest.raises(CollectError, match="shm"):
            collect_once(conn, str(tmp_path / "x.db"), config,
                         "2026-10-06", T0)
    assert any("collect_failed" in r.message for r in caplog.records)


# ---------- 方案 A(2026-10-07):快照完成识别与时效(docs/sessions/ ----------
# ---------- 2026-10-07-plan-a-snapshot-rules.md 规则 1/2)----------

def _write_snapshot(d, stamp, *, rows=1, break_tail=False, mtime_shift_s=0,
                    empty_schema=False, name=None):
    """造 td 风格备份件(名字时戳=mtime=内容时点,真实备份语义)。
    break_tail=截半模拟 backup 写一半;mtime_shift_s=事后改写错位;
    empty_schema=无关库(quick_check ok 但无窗口 schema)。"""
    import os
    p = d / (name or f"topic-digest-{stamp:%Y%m%dT%H%M%S}.db")
    c = sqlite3.connect(p)
    if not empty_schema:
        c.executescript(_UPSTREAM_DDL)
        sid = _add_source(c, "snap-src")
        for i in range(rows):
            _add_item(c, sid, f"https://example.com/s{i}", f"t{i}",
                      fetched=stamp - timedelta(hours=1), content="c")
    c.close()
    if break_tail:
        data = p.read_bytes()
        p.write_bytes(data[: len(data) // 2])
    os.utime(p, (stamp.timestamp() + mtime_shift_s,) * 2)
    return p


def _journal(*rounds):
    """合成 journalctl 输出(时间正序)。每轮=dict(path=..., ok=...,
    still_running=...);ok/running 二选一,默认 ok=True。"""
    lines = []
    host = "srv systemd[1]"
    for r in rounds:
        path = r.get("path")
        lines.append(f"2026-10-07T03:35:01+0800 {host}: Starting topic-digest nightly db backup...")
        if path:
            lines.append(f"2026-10-07T03:35:02+0800 srv python[9]: backup -> {path}; pruned 1")
        if r.get("still_running"):
            continue                       # stdout 已打印,进程未结束
        lines.append(f"2026-10-07T03:35:02+0800 {host}: topic-digest-backup.service: "
                     + ("Succeeded." if r.get("ok", True)
                        else "Failed with result 'exit-code'."))
    return "\n".join(lines) + "\n"


# 场景 3:有效已完成备份——journal 成功行+文件防线全过 → 选中并留痕
def test_resolve_picks_journal_success_file(env, caplog):
    conn, config, tmp_path = env
    d = tmp_path / "backups"; d.mkdir()
    snap = _write_snapshot(d, T0 - timedelta(hours=5))
    text = _journal(dict(path=str(snap)))
    with caplog.at_level("INFO", logger="nanmu_engine.collect"):
        got = collect_mod.resolve_upstream_snapshot(d, T0,
                                                    journal_text=text)
    assert got == str(snap)
    assert "snapshot_resolved" in caplog.text
    assert any("snapshot_resolved" in r.message for r in caplog.records)


# 场景 1:备份仍在生成(stdout 已打印但 invocation 未结束)→ 跳过,用上一份成功件
def test_resolve_skips_running_backup_uses_previous(env):
    conn, config, tmp_path = env
    d = tmp_path / "backups"; d.mkdir()
    prev = _write_snapshot(d, T0 - timedelta(hours=29))
    running = _write_snapshot(d, T0 - timedelta(hours=1), rows=1)
    text = _journal(dict(path=str(prev)),
                    dict(path=str(running), still_running=True))
    assert collect_mod.resolve_upstream_snapshot(d, T0,
                                                 journal_text=text) == str(prev)


# 场景 2:最新备份失败且残留文件名字最新 → 不取残留,回退上一份成功件
def test_resolve_ignores_failed_backup_leftover(env):
    conn, config, tmp_path = env
    d = tmp_path / "backups"; d.mkdir()
    good = _write_snapshot(d, T0 - timedelta(hours=29))
    leftover = _write_snapshot(d, T0 - timedelta(hours=1), break_tail=True)
    assert leftover.name > good.name      # 残留件名字更新——不得"取目录最新"
    text = _journal(dict(path=str(good)),
                    dict(path=str(leftover), ok=False))
    assert collect_mod.resolve_upstream_snapshot(d, T0,
                                                 journal_text=text) == str(good)


# 场景 4:快照过旧(最近成功件年龄>48h)→ E2 停止
def test_resolve_stops_when_snapshot_stale(env):
    conn, config, tmp_path = env
    d = tmp_path / "backups"; d.mkdir()
    snap = _write_snapshot(d, T0 - timedelta(hours=49))
    text = _journal(dict(path=str(snap)))
    with pytest.raises(CollectError, match="过旧"):
        collect_mod.resolve_upstream_snapshot(d, T0, journal_text=text)


# 场景 5a:无成功完成的备份任务 → 证据不足停止
def test_resolve_stops_when_no_success_record(env):
    conn, config, tmp_path = env
    d = tmp_path / "backups"; d.mkdir()
    _write_snapshot(d, T0 - timedelta(hours=1))   # 文件在也没用:无任务背书
    for text in ("", _journal(dict(path=None, ok=False)),
                 _journal(dict(path=str(d / "nonexistent.db")))):
        with pytest.raises(CollectError, match="证据不足"):
            collect_mod.resolve_upstream_snapshot(d, T0, journal_text=text)


# 防线:journal 说成功但文件侧不过(截断/错位/无 schema/目录外)→ 停,不倒退
@pytest.mark.parametrize("kw,why", [
    (dict(break_tail=True), "截断"),
    (dict(mtime_shift_s=3600), "错位"),
    (dict(empty_schema=True), "schema"),
])
def test_resolve_stops_when_file_guard_fails(env, kw, why):
    conn, config, tmp_path = env
    d = tmp_path / "backups"; d.mkdir()
    snap = _write_snapshot(d, T0 - timedelta(hours=5), **kw)
    text = _journal(dict(path=str(snap)))
    with pytest.raises(CollectError, match="防线"):
        collect_mod.resolve_upstream_snapshot(d, T0, journal_text=text)


def test_resolve_stops_when_file_outside_dir(env):
    conn, config, tmp_path = env
    d = tmp_path / "backups"; d.mkdir()
    other = tmp_path / "elsewhere"
    other.mkdir()
    snap = _write_snapshot(other, T0 - timedelta(hours=5))
    text = _journal(dict(path=str(snap)))
    with pytest.raises(CollectError, match="证据不足"):
        collect_mod.resolve_upstream_snapshot(d, T0, journal_text=text)


# 纯函数:journal 解析配对(倒序最近成功 invocation 的 backup-> 行)
def test_parse_journal_pairs_latest_success():
    parse = collect_mod._parse_backup_journal
    name = lambda tag: f"/opt/topic-digest/backups/topic-digest-{tag}.db"
    text = _journal(dict(path=name("20261005T193501")),
                    dict(path=name("20261006T193001"), ok=False),
                    dict(path=name("20261006T193501")))
    assert parse(text) == (name("20261006T193501"),
                           "2026-10-07T03:35:02+0800")
    assert parse("") is None


# 集成:collect_once 收快照目录,通道经 monkeypatch 注入
def test_collect_once_reads_snapshot_dir_end_to_end(
        env, monkeypatch, caplog):
    conn, config, tmp_path = env
    d = tmp_path / "backups"; d.mkdir()
    _write_snapshot(d, T0 - timedelta(hours=25), rows=1)
    snap = _write_snapshot(d, T0 - timedelta(hours=5), rows=2)
    monkeypatch.setattr(collect_mod, "_fetch_backup_journal",
                        lambda: _journal(dict(path=str(snap))))
    with caplog.at_level("INFO", logger="nanmu_engine.collect"):
        out = collect_once(conn, str(d), config, "2026-10-06", T0)
    assert out.status == "frozen" and len(out.manifest) == 2
    assert "snapshot_resolved" in caplog.text


def test_collect_once_snapshot_channel_unreadable_e2(env, monkeypatch):
    """证据通道(journalctl)不可读=权限缺口,E2 停止并说明,不改上游。"""
    conn, config, tmp_path = env
    d = tmp_path / "backups"; d.mkdir()

    def boom(*args, **kwargs):
        raise OSError("permission denied")
    monkeypatch.setattr("subprocess.run", boom)   # 通道层失败,_fetch 转换
    with pytest.raises(CollectError, match="证据通道"):
        collect_once(conn, str(d), config, "2026-10-06", T0)
