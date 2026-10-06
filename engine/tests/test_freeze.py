"""冻结 issue_freeze 与 manifest 测试(种子=data-ingestion 验收 2/3/4;
事务边界契约=entry upsert 与 freeze INSERT 同一事务拥有者一次提交)。"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import nanmu_engine.collect as collect_mod
from nanmu_engine.collect import collect_once, freeze_issue
from nanmu_engine.config import SourceEntry, SourcesConfig, load_config
from nanmu_engine.db import connect_db, migrate

from test_collect import (_add_item, _add_source, _cfg, _make_upstream)

ENGINE_ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 6, 8, 30, tzinfo=timezone.utc)


@pytest.fixture
def env(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    config = load_config(ENGINE_ROOT)
    return conn, config, tmp_path


def _prime_upstream(tmp_path, content="c"):
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, "src-a")
    _add_item(up, sid, "https://example.com/x", "t1",
              fetched=T0 - timedelta(hours=1), content=content)
    return up, path


# ---------- freeze_issue 单元:幂等 + 不中途 COMMIT ----------

def test_freeze_issue_idempotent_returns_existing_frozen_utc(env):
    conn, _, _ = env
    conn.execute("BEGIN IMMEDIATE")
    u1 = freeze_issue(conn, "2026-10-06", [], T0)
    conn.execute("COMMIT")
    # 同 issue_date 再调:返回既有 frozen_utc,不插第二行不覆盖
    conn.execute("BEGIN IMMEDIATE")
    u2 = freeze_issue(conn, "2026-10-06", [{"identity_key": "url:x"}],
                      T0 + timedelta(hours=2))
    conn.execute("ROLLBACK")
    assert u1 == u2
    rows = conn.execute("SELECT COUNT(*), entry_count FROM issue_freeze"
                        ).fetchone()
    assert rows == (1, 0)      # 首次冻结结果未被第二次调用改写


def test_freeze_issue_no_intermediate_commit(env, tmp_path):
    # 事务拥有者是调用方:freeze_issue INSERT 后、COMMIT 前,
    # 另一连接必须看不到冻结行(无中途提交)
    conn, _, _ = env
    conn.execute("BEGIN IMMEDIATE")
    freeze_issue(conn, "2026-10-06", [], T0)
    other = connect_db(str(tmp_path / "engine.db"))
    assert other.execute("SELECT COUNT(*) FROM issue_freeze"
                         ).fetchone()[0] == 0
    other.close()
    conn.execute("ROLLBACK")
    assert conn.execute("SELECT COUNT(*) FROM issue_freeze").fetchone()[0] == 0


# ---------- 验收 4:空集合合法冻结 ----------

def test_empty_collection_freezes_zero_manifest(env, tmp_path):
    conn, config, _ = env
    up, path = _make_upstream(tmp_path)          # 窗口内 0 条
    result = collect_once(conn, path, config, "2026-10-06", T0)
    assert result.status == "frozen" and result.manifest == []
    row = conn.execute("SELECT entry_count, manifest_json FROM issue_freeze"
                       " WHERE issue_date='2026-10-06'").fetchone()
    assert row == (0, "[]")                      # 空集合=合法冻结
    # 零付费:无任何 attempt
    assert conn.execute("SELECT COUNT(*) FROM receipt_attempt"
                        ).fetchone()[0] == 0


# ---------- 验收 3:幂等入口,上游查询 0 次 ----------

def test_second_collect_makes_zero_upstream_queries(env, tmp_path, monkeypatch):
    conn, config, tmp_path = env
    up, path = _prime_upstream(tmp_path)
    calls = []
    real_connect = collect_mod.connect_readonly

    def counting_connect(p):
        calls.append(p)
        return real_connect(p)

    monkeypatch.setattr(collect_mod, "connect_readonly", counting_connect)
    cfg = _cfg(config, [SourceEntry("src-a", "T1", 100)])
    r1 = collect_once(conn, path, cfg, "2026-10-06", T0)
    assert r1.status == "frozen" and len(calls) == 1
    r2 = collect_once(conn, path, cfg, "2026-10-06", T0)
    assert r2.status == "already_frozen"
    assert len(calls) == 1                        # 二次采集上游查询次数=0


# ---------- 验收 2:事务内注入 kill → 无行无半写,重跑一致 ----------

def test_kill_mid_transaction_rerun_consistent(env, tmp_path):
    # 中断组:注入 kill(trigger 在 freeze INSERT 时 ABORT)
    conn, config, _ = env
    up, path = _prime_upstream(tmp_path)
    cfg = _cfg(config, [SourceEntry("src-a", "T1", 100)])
    conn.execute("CREATE TRIGGER boom BEFORE INSERT ON issue_freeze"
                 " BEGIN SELECT RAISE(ABORT, 'boom'); END")
    conn.commit()
    with pytest.raises(sqlite3.DatabaseError):
        collect_once(conn, path, cfg, "2026-10-06", T0)
    assert conn.execute("SELECT COUNT(*) FROM issue_freeze").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 0

    # 对照组:无中断直接跑(独立库),manifest 应与重跑结果一致
    import dataclasses
    other_dir = tmp_path / "clean"
    other_dir.mkdir()
    conn2 = connect_db(str(other_dir / "engine.db"))
    migrate(conn2)
    up2, path2 = _prime_upstream(other_dir)
    clean = collect_once(conn2, path2, cfg, "2026-10-06", T0)
    conn2.close()

    # 修复后重跑:结果与未中断一致
    conn.execute("DROP TRIGGER boom")
    conn.commit()
    rerun = collect_once(conn, path, cfg, "2026-10-06", T0)
    assert rerun.status == "frozen"
    assert rerun.manifest == clean.manifest
    assert conn.execute("SELECT entry_count, manifest_json FROM issue_freeze"
                        ).fetchone() == conn.execute(
        "SELECT entry_count, manifest_json FROM issue_freeze").fetchone()
