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
import re
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

# 方案 A(2026-10-07):上游读取复用 td 每夜 Online Backup 快照
# (conn.backup() 事务一致,append-only 命名,写后不改)。完成识别与
# 时效规则=docs/sessions/2026-10-07-plan-a-snapshot-rules.md:
# **完成证明=任务级证据链**(backup.py 先创建最终名再 backup,文件名/
# 存在/大小稳定都不构成完成证明;quick_check 等文件检查只是防线,不得
# 替代完成状态):journalctl -u topic-digest-backup.service 中最近一次
# 成功 invocation 打印的 `backup -> <path>` 行把具体文件与成功任务关联;
# 备份仍在生成/最新失败(残留件名字最新)→ 回退上一份成功件——引擎
# 从不"取目录最新 .db"。选中件再过文件防线(名字/mtime/quick_check/
# schema)与年龄上限(48h;03:30 备份/08:30 日报节奏下正常≈5h、错过
# 一夜≈29h,数据延迟最迟次日 08:30 处理,异常时无上界直至 E2 停止)。
# 任何一环不过=E2 停止,不降级直读活库、不取无证明件。
_SNAPSHOT_NAME_RE = re.compile(
    r"^topic-digest-(\d{8}T\d{6})\.db$")
_SNAPSHOT_STAMP_FMT = "%Y%m%dT%H%M%S"
_SNAPSHOT_MAX_AGE_H = 48       # 容一夜备份失败;两夜无成功件即停
_SNAPSHOT_MTIME_TOL_S = 300    # backup 耗时量级;更偏=文件被动过
_BACKUP_LINE_RE = re.compile(
    r"backup -> (\S+?topic-digest-\d{8}T\d{6}\.db)")
_BACKUP_UNIT = "topic-digest-backup.service"
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


def freeze_issue(engine_conn: sqlite3.Connection, issue_date: str,
                 manifest: list, now_utc: datetime) -> str:
    """在**调用方事务内**写冻结行(不 COMMIT——事务拥有者是
    collect_once,entry upsert 与本 INSERT 一次提交);行已存在=幂等
    返回既有 frozen_utc,不插第二行不覆盖。空 manifest 合法(空集合
    是合法冻结)。返回 frozen_utc。
    """
    existing = engine_conn.execute(
        "SELECT frozen_utc FROM issue_freeze WHERE issue_date=?",
        (issue_date,)).fetchone()
    if existing is not None:
        return existing[0]
    frozen_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    engine_conn.execute(
        "INSERT INTO issue_freeze (issue_date, frozen_utc, entry_count,"
        " manifest_json) VALUES (?,?,?,?)",
        (issue_date, frozen_utc, len(manifest),
         json.dumps(manifest, ensure_ascii=False)))
    return frozen_utc


class CollectError(Exception):
    """E2:上游读取失败(打不开/权限/schema 依赖红/快照证据不足或过旧)。

    digest_issue failed 行由单元五按该分类落库;本模块以日志为最小证据。
    """


def _snapshot_evidence(path: Path) -> str | None:
    """单件完成证据校验;通过返回 None,不通过返回失败原因(记日志)。"""
    m = _SNAPSHOT_NAME_RE.match(path.name)
    if m is None:
        return "名字不匹配"
    stamp = datetime.strptime(m.group(1), _SNAPSHOT_STAMP_FMT).replace(
        tzinfo=timezone.utc)   # td backup() 以 UTC 命名(backup.py 源码)
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime,
                                        tz=timezone.utc)
    except OSError as exc:
        return f"stat 失败:{exc}"
    if abs((mtime - stamp).total_seconds()) > _SNAPSHOT_MTIME_TOL_S:
        return "mtime 与名字时戳错位"
    cutoff = (stamp - timedelta(hours=_WINDOW_HOURS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")          # 窗口参数形态;limit 0 仅验 schema
    try:
        conn = connect_readonly(str(path), immutable=True)
        try:
            check = conn.execute("PRAGMA quick_check").fetchone()
            if not check or check[0] != "ok":
                return f"quick_check={check[0] if check else '?'}"
            conn.execute(_WINDOW_SQL, (cutoff,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"读取失败:{exc}"
    return None


def _parse_backup_journal(text: str) -> tuple[str, str] | None:
    """解析 journalctl 输出(时间正序),返回最近一次**成功完成**任务的
    (产物绝对路径, 成功时刻);无成功任务=None。

    配对规则:倒序找 systemd 成功结局行(Succeeded/Deactivated
    successfully),再向前(更早行)找同 invocation 的 `backup -> <path>`
    stdout 行;中间隔着另一条结局/Starting 行=越界放弃。失败结局
    (Failed)与无结局(任务仍在生成,stdout 先于进程退出打印)的
    backup-> 行不配对——天然实现"进行中跳过、最新失败回退上一份"。
    """
    lines = text.splitlines()

    def _kind(line: str) -> str | None:
        low = line.lower()
        if "succeeded" in low or "deactivated successfully" in low:
            return "ok"
        if "failed" in low or "starting" in low:
            return "boundary"
        return None

    for i in range(len(lines) - 1, -1, -1):
        if _kind(lines[i]) != "ok":
            continue
        for j in range(i - 1, -1, -1):
            m = _BACKUP_LINE_RE.search(lines[j])
            if m:
                ts = lines[i].split()[0] if lines[i].split() else ""
                return m.group(1), ts
            if _kind(lines[j]) == "boundary":
                break                    # 越界:该 Succeeded 轮无产物行
    return None


def _fetch_backup_journal() -> str:
    """真实装配:读备份 unit 日志(nanmu 无特权可读,2026-10-07 服务器
    实测)。通道不可读=完成证明无法获得,E2 停止并报最小权限缺口,
    不修改上游。"""
    import subprocess
    try:
        out = subprocess.run(
            ["journalctl", "-u", _BACKUP_UNIT, "--no-pager",
             "-o", "short-iso", "-n", "500"],
            capture_output=True, text=True, timeout=15, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CollectError(
            f"E2 备份完成证据通道不可读(journalctl -u {_BACKUP_UNIT}):"
            f"{exc};最小权限缺口:nanmu 需可读该 unit 日志;未获授权"
            f"不修改上游,引擎 E2 停止") from exc
    return out.stdout


def resolve_upstream_snapshot(dir_path: Path, now_utc: datetime, *,
                              journal_text: str | None = None) -> str:
    """选上游快照:完成证明=journal 任务级证据链,文件检查只是防线。

    步骤:①journal(注入 text 或真实通道)取最近成功任务的产物路径;
    ②路径必须在配置目录内且文件在;③文件防线(名字/mtime/quick_check/
    schema);④年龄上限(名字时戳=内容时点)。任何一环不过=CollectError
    (E2)停止,不降级直读活库、不取无完成证明的件、不倒退更旧件。
    """
    if journal_text is None:
        journal_text = _fetch_backup_journal()
    parsed = _parse_backup_journal(journal_text)
    if parsed is None:
        raise CollectError(
            "E2 上游快照证据不足:journal 无成功完成的备份任务记录"
            f"(unit={_BACKUP_UNIT};备份仍在生成/全部失败/日志被轮转"
            "均属此类,人工核对后重试)")
    snap_str, ok_ts = parsed
    snap = Path(snap_str)
    try:
        snap.resolve().relative_to(Path(dir_path).resolve())
    except ValueError:
        raise CollectError(
            f"E2 上游快照证据不足:成功任务关联文件不在配置目录"
            f" {dir_path}({snap})") from None
    if not snap.is_file():
        raise CollectError(
            f"E2 上游快照证据不足:成功任务关联文件缺失({snap.name})")
    reason = _snapshot_evidence(snap)
    if reason is not None:
        raise CollectError(
            f"E2 快照防线不过:{snap.name} {reason}——journal 与文件"
            f"不一致属环境异常,不倒退更旧件,人工核对")
    stamp = datetime.strptime(
        _SNAPSHOT_NAME_RE.match(snap.name).group(1),
        _SNAPSHOT_STAMP_FMT).replace(tzinfo=timezone.utc)
    age_h = (now_utc - stamp).total_seconds() / 3600
    if age_h > _SNAPSHOT_MAX_AGE_H:
        raise CollectError(
            f"E2 上游快照过旧:{snap.name} 内容时点距今 {age_h:.1f}h"
            f"(上限 {_SNAPSHOT_MAX_AGE_H}h);错过备份的数据最迟次日"
            f"08:30 处理,异常时延迟无上界——停止待人工核对")
    logger.info("stage=collect event=snapshot_resolved file=%s"
                " content_ts=%s age_h=%.1f task_succeeded=%s",
                snap.name, stamp.strftime(_SNAPSHOT_STAMP_FMT), age_h,
                ok_ts)
    return str(snap)


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

    上游经 connect_readonly(mode=ro)直读。审计修正(2026-10-07):文件级
    快照方案撤回——裸拷主库+quick_check 不构成一致性保证(checkpoint 中途
    撕裂结构合法不可检),且漏 WAL 内已提交数据;无 -shm 写权即无法参与
    SQLite 锁协议,既有权限下无安全读法,此时 E2 停止并在错误信息中报告
    最小权限缺口,不擅改上游、不降级读取。

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

    # 1) 只读窗口查询(规模护栏:行数与耗时)。upstream_path 为目录时
    #    =方案 A 快照目录:先解析证据齐全的最新备份件,再 immutable 读
    #    (快照 append-only 写后不改,immutable 语义严格成立;活库
    #    永不走 immutable——并发检查点下会撕裂)。
    try:
        up_dir = Path(upstream_path)
        immutable = False
        if up_dir.is_dir():
            upstream_path = resolve_upstream_snapshot(up_dir, now_utc)
            immutable = True
        upstream = connect_readonly(upstream_path, immutable=immutable)
        cutoff = (now_utc - timedelta(hours=_WINDOW_HOURS)).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        started = time.perf_counter()
        rows = upstream.execute(_WINDOW_SQL, (cutoff,)).fetchall()
        query_ms = int((time.perf_counter() - started) * 1000)
        upstream.close()
    except sqlite3.Error as exc:
        detail = str(exc)
        if "readonly" in detail.lower():
            detail += (";最小权限缺口:上游 WAL 库的 mode=ro 读者须能在上游"
                       "数据目录创建/写 -shm/-wal(当前用户无此权限),或由上游"
                       "暴露一致快照;未获授权不修改上游,引擎 E2 停止")
        logger.error("stage=collect event=collect_failed error_class=E2"
                     " upstream=%s message=%s", upstream_path, detail)
        raise CollectError(f"E2 上游读取失败:{detail}") from exc
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

        freeze_issue(engine_conn, issue_date, members, now_utc)
        engine_conn.execute("COMMIT")       # 冻结确认事件在此刻发生
    except Exception:
        try:
            engine_conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    return CollectResult("frozen", manifest=members, item_total=len(rows),
                         query_ms=query_ms)
