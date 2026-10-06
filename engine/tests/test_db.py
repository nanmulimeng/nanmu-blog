"""db 单一入口与 12 表迁移测试(DDL 真相源=spec §5.3)。

种子:Task 3 brief + coding-standards SQLite 约定(未知较新版本拒绝,
不靠删库/重置让门禁变绿)。
"""

import sqlite3

import pytest

from nanmu_engine.db import connect_db, connect_readonly, migrate

EXPECTED_TABLES = {
    "entry", "receipt", "receipt_attempt", "budget", "analysis",
    "override", "digest_issue", "issue_freeze", "api_usage",
    "summary", "notify_sent", "engine_meta",
}


def test_fresh_db_writes_pay_paused_default_zero(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    # 建库即写默认 0 —— 键缺失不可能是正常新库状态(scheduling-ops 规则 9)
    assert conn.execute(
        "SELECT value FROM engine_meta WHERE key='pay_paused'"
    ).fetchone()[0] == "0"
    conn.close()


def test_table_count_is_12(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")
    }
    assert tables == EXPECTED_TABLES
    # 抽查联合核验轮扩展列存在(spec §5.3)
    attempt_cols = {r[1] for r in conn.execute("PRAGMA table_info(receipt_attempt)")}
    assert {"attempt_origin", "error_class", "fail_detail_json"} <= attempt_cols
    issue_cols = {r[1] for r in conn.execute("PRAGMA table_info(digest_issue)")}
    assert {"ops_json", "content_sha256"} <= issue_cols
    freeze_cols = {r[1] for r in conn.execute("PRAGMA table_info(issue_freeze)")}
    assert {"paused", "paused_reason", "paused_utc"} <= freeze_cols
    conn.close()


def test_connect_db_sets_pragmas(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    conn.close()


def test_migrate_idempotent_and_versioned(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    migrate(conn)  # 幂等
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.close()


def test_unknown_newer_version_rejected_without_reset(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    conn.execute("PRAGMA user_version = 2")  # 模拟未来版本库
    conn.commit()
    conn.close()

    conn2 = connect_db(str(tmp_path / "engine.db"))
    with pytest.raises(Exception, match="user_version|未知|版本"):
        migrate(conn2)
    # 拒绝启动写入:版本未被重置,表结构未被清空
    assert conn2.execute("PRAGMA user_version").fetchone()[0] == 2
    tables = {
        row[0] for row in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")
    }
    assert tables == EXPECTED_TABLES
    conn2.close()


def test_connect_readonly_rejects_writes(tmp_path):
    db = tmp_path / "engine.db"
    conn = connect_db(str(db))
    migrate(conn)
    conn.close()

    ro = connect_readonly(str(db))
    assert ro.execute("SELECT COUNT(*) FROM entry").fetchone()[0] == 0
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO entry (identity_key, url, title, discovered_utc) "
                   "VALUES ('k', 'u', 't', 'now')")
    ro.close()
