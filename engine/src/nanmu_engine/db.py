"""engine.db 单一可写入口与版本化迁移(DDL 真相源=spec §5.3)。

本项目可写连接只经 connect_db(WAL/busy_timeout=5000/foreign_keys=ON);
topic-digest 上游只读经 connect_readonly(file:...?mode=ro,不执行写
PRAGMA,不迁移)。迁移按 PRAGMA user_version 版本化:未知较新版本拒绝
启动写入,不重置不删库(coding-standards SQLite 约定)。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA_V1 = """
-- 候选条目(topic-digest 条目的快照,判重后)
CREATE TABLE entry (
  id INTEGER PRIMARY KEY,
  identity_key TEXT NOT NULL UNIQUE,
  url TEXT NOT NULL, title TEXT NOT NULL,
  source_name TEXT NOT NULL, source_tier TEXT NOT NULL DEFAULT 'T2',
  published_utc TEXT, discovered_utc TEXT NOT NULL,
  content_text TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','scored','selected','rejected','used')),
  claim_issue TEXT
);
CREATE INDEX idx_entry_discovered ON entry(discovered_utc DESC);

-- 逻辑回执(每个请求身份一条;每次网络尝试另写 receipt_attempt)
CREATE TABLE receipt (
  id INTEGER PRIMARY KEY,
  logical_key TEXT NOT NULL UNIQUE,
  provider TEXT NOT NULL, endpoint TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  service TEXT NOT NULL,
  purpose TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK(status IN ('pending','received','completed','failed','unknown')),
  request_digest TEXT,
  unknown_retry_used INTEGER NOT NULL DEFAULT 0,
  response_json TEXT, usage_json TEXT,
  cost_cny REAL,
  attempts INTEGER NOT NULL DEFAULT 0,
  created_utc TEXT NOT NULL, completed_utc TEXT
);
CREATE INDEX idx_receipt_open ON receipt(status) WHERE status IN ('pending','unknown');

-- 每次网络尝试单独记录,用于滑动窗口与金额预占
CREATE TABLE receipt_attempt (
  id INTEGER PRIMARY KEY,
  receipt_id INTEGER NOT NULL REFERENCES receipt(id),
  attempt_no INTEGER NOT NULL,
  issue_date TEXT,
  started_utc TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('pending','received','unknown','failed')),
  attempt_origin TEXT NOT NULL
    CHECK(attempt_origin IN ('initial','retry','unknown_retry')),
  error_class TEXT CHECK(error_class IN ('no_retry','retryable','unknown') OR error_class IS NULL),
  fail_detail_json TEXT,
  reserved_micro_cny INTEGER NOT NULL CHECK(reserved_micro_cny >= 0),
  actual_micro_cny INTEGER CHECK(actual_micro_cny >= 0),
  usage_json TEXT, pricing_version TEXT NOT NULL,
  reconcile_json TEXT,
  UNIQUE(receipt_id, attempt_no)
);
CREATE INDEX idx_attempt_started ON receipt_attempt(started_utc);

-- 三级预算(次数限制;行缺失=配置错误,拒绝付费;任一档 ≤0 = 立即停用)
CREATE TABLE budget (
  service TEXT PRIMARY KEY,
  per_minute INTEGER NOT NULL, per_hour INTEGER NOT NULL, per_day INTEGER NOT NULL
);

-- 评分记录(append-only)
CREATE TABLE analysis (
  id INTEGER PRIMARY KEY,
  entry_id INTEGER NOT NULL REFERENCES entry(id),
  prompt_version TEXT NOT NULL,
  model TEXT NOT NULL,
  score_1 INTEGER, score_2 INTEGER,
  selected INTEGER NOT NULL DEFAULT 0,
  receipt_ids TEXT NOT NULL,
  created_utc TEXT NOT NULL
);
CREATE INDEX idx_analysis_entry ON analysis(entry_id, id DESC);

-- 人工覆盖(优先于评分判断,不绕过来源/输入安全/预算限制)
CREATE TABLE override (
  identity_key TEXT PRIMARY KEY,
  action TEXT NOT NULL CHECK(action IN ('force_include','exclude')),
  reason TEXT, created_utc TEXT NOT NULL
);

-- 每期日报
CREATE TABLE digest_issue (
  issue_date TEXT NOT NULL UNIQUE,
  entry_ids TEXT NOT NULL DEFAULT '[]',
  markdown_path TEXT,
  git_commit TEXT,
  content_sha256 TEXT,
  ops_json TEXT,
  cost_cny REAL NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','submitted','published','failed')),
  created_utc TEXT NOT NULL,
  fail_reason TEXT,
  updated_utc TEXT,
  last_exit INTEGER,
  last_run_utc TEXT,
  withdrawn_utc TEXT,
  withdraw_commit TEXT,
  relisted_utc TEXT,
  relist_commit TEXT,
  CHECK(status = 'failed' OR markdown_path IS NOT NULL)
);

-- 期候选冻结确认(collect 结束单事务写入;行存在且完整=冻结确认事件)
CREATE TABLE issue_freeze (
  issue_date TEXT PRIMARY KEY,
  frozen_utc TEXT NOT NULL,
  entry_count INTEGER NOT NULL CHECK(entry_count >= 0),
  manifest_json TEXT NOT NULL,
  paused INTEGER NOT NULL DEFAULT 0 CHECK(paused IN (0,1)),
  paused_reason TEXT,
  paused_utc TEXT
);

-- 月度成本聚合(报表投影;不作调用授权依据)
CREATE TABLE api_usage (
  month TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
  tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
  cost_cny REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (month, provider, model)
);

-- 摘要记录(append-only;组装取当前身份最新行)
CREATE TABLE summary (
  id INTEGER PRIMARY KEY,
  entry_id INTEGER NOT NULL REFERENCES entry(id),
  prompt_version TEXT NOT NULL,
  model TEXT NOT NULL,
  title_zh TEXT NOT NULL, summary TEXT NOT NULL, reason TEXT NOT NULL,
  tags_json TEXT,
  receipt_ids TEXT NOT NULL,
  created_utc TEXT NOT NULL
);
CREATE INDEX idx_summary_entry ON summary(entry_id, id DESC);

-- 通知发送记录(同 key UPSERT,不另起行)
CREATE TABLE notify_sent (
  dedup_key TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  sent_utc TEXT NOT NULL,
  result TEXT NOT NULL
);

-- 全局运行标志与校准记录(pay_paused 建库即写默认 0;校准契约=units/model-calls.md 规则 11)
CREATE TABLE engine_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_utc TEXT NOT NULL
);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect_db(path: str) -> sqlite3.Connection:
    """本项目唯一可写连接入口。"""
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def connect_readonly(path: str) -> sqlite3.Connection:
    """topic-digest 上游只读连接(mode=ro;不执行写 PRAGMA,不迁移)。

    WAL 库的 ro 读者须能在库所在目录创建/写 -shm;无此权限时打开后
    首次访问数据页报 SQLITE_READONLY——collect 层将其转 E2 并附最小
    权限缺口说明(审计修正 2026-10-07:文件级快照不构成一致性保证,
    已撤回;详见 collect_once docstring)。"""
    uri = Path(path).resolve().as_uri().replace("file:///", "file:/")
    return sqlite3.connect(uri + "?mode=ro", uri=True)


def migrate(conn: sqlite3.Connection) -> None:
    """版本化迁移。空库建 12 表,**单事务**(DDL 逐条 + engine_meta 默认
    pay_paused=0 + user_version 同一 BEGIN IMMEDIATE…COMMIT):中途崩溃
    整体回滚,库保持空且 version 0 → 可重入,不产生"非空但 version 0"
    死库(executescript 会先隐式 COMMIT,故逐条执行)。

    未知较新版本(> 当前已知)→ 抛错拒绝,不重置不删库。
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        raise RuntimeError(
            f"engine.db user_version={version} 高于本程序已知版本 "
            f"{SCHEMA_VERSION}:疑似程序回退,拒绝启动写入(不重置)")
    if version == SCHEMA_VERSION:
        return  # 已最新,幂等

    # version 0:空库初始化(非空库带 version 0 = 异常态,拒绝猜测结构)
    objects = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
    if objects:
        raise RuntimeError(
            "engine.db 非空但 user_version=0:结构未知,拒绝迁移(不猜测、不删库)")

    # 注释行内含 ASCII 分号,先剥离注释再按 ';' 切分(DDL 本体无内嵌分号)
    body = "\n".join(
        line for line in _SCHEMA_V1.splitlines()
        if not line.lstrip().startswith("--"))
    statements = [s for s in body.split(";") if s.strip()]
    try:
        conn.execute("BEGIN IMMEDIATE")
        for stmt in statements:
            conn.execute(stmt)
        conn.execute(
            "INSERT INTO engine_meta (key, value, updated_utc) "
            "VALUES ('pay_paused', '0', ?)", (_utc_now(),))
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
