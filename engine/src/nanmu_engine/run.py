"""调度运行序(scheduling-ops §3 规则 1-2)。

单次进程:flock 单实例(main 层)→config/预算校验(pay_paused=1 或键
缺失=跳过新增付费部分,只读照常,仅显式 0 放行)→**先恢复存量未完成期**
(issue_date 升序;submitted 只读确认→draft 发布恢复→生成中续跑;paused
跳过;恢复总预算 recover_budget_s,耗尽=保存状态继续新期)→当天新期全链
→汇总→收尾写 last_exit/last_run_utc。退出码优先级 1→2→4→3→0
(design.md 错误矩阵)。截止锚点=issue_freeze.frozen_utc 唯一:D 与 D+1
两触发窗,D+2 起不自动开始;submitted 只读确认不受限。

同轮 E3/E4 retryable 不忙等(design.md"不让单次进程忙等"):保存状态
留待下次调度,名额由 ledger 持久化计数跨运行生效。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from nanmu_engine.assemble import AssemblyPaused, assemble_issue, write_draft
from nanmu_engine.collect import CollectError, collect_once
from nanmu_engine.config import Config, ConfigError
from nanmu_engine.ledger import (_money_used, _month_window,
                                 compute_n_new, issue_cost_snapshot,
                                 reusable_scores)
from nanmu_engine.notify import notify_event, notify_monthly
from nanmu_engine.prescreen import prescreen
from nanmu_engine.publish import (ManualIntervention, PublishContext,
                                  publish_issue, recover_issue,
                                  stale_cost_issues)
from nanmu_engine.score import (_truncate_user, build_score_ctx,
                                 check_prompt_fits, score_entry,
                                 score_reuse_ctx)
from nanmu_engine.select import (apply_selection, check_claim_invariant,
                                 compute_final_set, decide_selection,
                                 release_abandoned_issue)
from nanmu_engine.summarize import understand_entry
from nanmu_engine.token_count import TokenizerUnavailable

logger = logging.getLogger(__name__)

RECOVER_BUDGET_S = 600.0        # 恢复阶段总预算(config 运行参数初值)
_EXIT_PRIORITY = (1, 2, 4, 3, 0)  # design.md:不得以部分成功覆盖需排查错误


def _log_sender(dedup_key: str, message: str) -> str:
    """默认发送体=M1 结构化日志(渠道凭据部署期接入;scheduling-ops §9)。"""
    logger.info("stage=notify event=send key=%s message=%s", dedup_key,
                message)
    return "logged"


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pick_exit(codes: list[int]) -> int:
    present = set(codes)
    for code in _EXIT_PRIORITY:
        if code in present and code != 0:
            return code
    return 0


def _shanghai_today(now: datetime) -> str:
    return (now.astimezone(timezone(timedelta(hours=8))).date()
            .isoformat())


def _read_pay_paused(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT value FROM engine_meta WHERE key='pay_paused'").fetchone()
    return row[0] if row else None


def _auto_eligible(frozen_utc: str, today: str) -> bool:
    """D 与 D+1 两触发窗(锚点=frozen_utc 唯一;晚 push/updated_utc 不延长)。"""
    try:
        return (date.fromisoformat(today)
                - date.fromisoformat(frozen_utc[:10])).days <= 1
    except ValueError:
        return False


# ---------- 通知(去重与发送统一走 notify.py;发送体注入) ----------


def _fail_issue(conn: sqlite3.Connection, issue_date: str,
                reason: str, *, send: Callable[[str, str], str] | None = None
                ) -> None:
    """落 failed 行(E2 子类/E6 子类/no_candidates/zero_qualified;
    §3 规则 6 字段映射的失败阶段/原因项)+ 失败通知(E2/E6/无合格为
    两期类:首期抑制由 notify_event 判定,此处只管发)。"""
    now = _now_str()
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, status,"
            " created_utc, fail_reason, updated_utc)"
            " VALUES (?, '[]', 'failed', ?, ?, ?)"
            " ON CONFLICT(issue_date) DO UPDATE SET status='failed',"
            " fail_reason=excluded.fail_reason, updated_utc=excluded.updated_utc",
            (issue_date, now, reason, now))
    notify_event(conn, reason, issue_date,
                 f"{issue_date} 期失败:{reason}(退出码非零,人工核对)",
                 send=send or _log_sender)


# ---------- 未完成期清单(自动恢复资格运行时计算,不加列) ----------

def _open_issues(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """(issue_date, kind):digest_issue draft/submitted 行 + 冻结在而无行
    (生成中);升序。published/failed 不进(failed 不自动重跑——冻结行
    在但期已终态的,同样不进:评分全挂落 failed 后冻结行仍在是常态)。"""
    status_by_date = dict(conn.execute(
        "SELECT issue_date, status FROM digest_issue"
        " WHERE status IN ('draft','submitted')").fetchall())
    terminal = {d for (d,) in conn.execute(
        "SELECT issue_date FROM digest_issue"
        " WHERE status IN ('published','failed')")}
    out: list[tuple[str, str]] = []
    for (d,) in conn.execute(
            "SELECT issue_date FROM issue_freeze ORDER BY issue_date"):
        if d not in status_by_date and d not in terminal:
            out.append((d, "generating"))
    out.extend((d, s) for d, s in sorted(status_by_date.items()))
    out.sort()
    return out


def _final_keys_from_entry_ids(conn: sqlite3.Connection,
                               issue_date: str) -> list[str]:
    row = conn.execute("SELECT entry_ids FROM digest_issue WHERE issue_date=?",
                       (issue_date,)).fetchone()
    ids = json.loads(row[0] or "[]") if row else []
    if not ids:
        return []
    ph = ",".join("?" * len(ids))
    return [k for (k,) in conn.execute(
        f"SELECT identity_key FROM entry WHERE id IN ({ph})", ids)]


# ---------- 生成全链(冻结在→预筛→评分→入选→摘要→组装→发布) ----------

def _generate_issue(conn: sqlite3.Connection, config: Config, issue_date: str,
                    ctx: PublishContext, *, paid_allowed: bool,
                    transport, now: datetime,
                    notify_send: Callable[[str, str], str] | None = None
                    ) -> int:
    """生成中续跑与当天新期共用(冻结在=续跑语义:manifest/回执复用)。
    返回该期退出码。pay_paused 期间:付费调用跳过、期保持生成中(不落
    failed);有合格产物(复用侧齐)仍可组装发布。"""
    row = conn.execute(
        "SELECT manifest_json FROM issue_freeze WHERE issue_date=?",
        (issue_date,)).fetchone()
    if row is None:
        logger.error("stage=run event=no_freeze issue=%s", issue_date)
        return 3
    manifest = json.loads(row[0])
    if not manifest:
        _fail_issue(conn, issue_date, "no_candidates",
                        send=notify_send or _log_sender)
        return 3

    occupancy = {k: (s, c) for k, s, c in conn.execute(
        "SELECT identity_key, status, claim_issue FROM entry")}
    overrides = dict(conn.execute(
        "SELECT identity_key, action FROM override").fetchall())
    override_exclude = {k for k, a in overrides.items() if a == "exclude"}

    usable: list[dict] = []
    for m in manifest:      # 复用判定与实际请求同身份(截断后输入入哈希)
        try:
            m["user_text"], _count = _truncate_user(
                config, m["title"], m["content_text"] or "",
                config.prompts.score.text)
        except ValueError:      # title_too_long:单条剔除,不中断整期
            logger.warning("stage=run event=member_excluded key=%s"
                           " reason=title_too_long", m["identity_key"])
            continue
        except TokenizerUnavailable as exc:   # 计数不可得=E1 拒启动
            logger.error("stage=run event=E1.tokenizer message=%s", exc)
            return 2
        usable.append(m)
    identity_ctx = score_reuse_ctx(config)   # 与 score 请求同一身份构造
    reuse_snapshot = reusable_scores(conn, usable, identity_ctx)
    n_new = compute_n_new(conn, config, issue_date, now=now)
    pre = prescreen(usable, config, issue_date, occupancy,
                    override_exclude, reuse_snapshot, n_new)

    skipped_pay = False
    statuses: list[str] = []
    for m in [*pre.to_score, *pre.recoverable]:
        snap = reuse_snapshot.get(m["identity_key"], {})
        if not paid_allowed and snap.get("needs"):
            skipped_pay = True            # 新增付费跳过;双分齐者纯复用
            continue
        statuses.append(score_entry(
            conn, config, m, issue_date=issue_date,
            transport=transport, now=now).status)

    # 入选候选=通过预筛四去向的成员(to_score+recoverable)且 analysis 行
    # 关联回执就是当前请求身份——已发布/被排除/被他期占用/被截断的成员
    # 不得借旧 analysis 行绕过预筛重新入选(重复发布,spec §5.2);同
    # entry 换正文(上游重抓)不得沿用旧输入的分数(R2:按 receipt_ids→
    # request_hash 与当前 score-1/score-2 身份比对过滤)
    entry_ids = [m["entry_id"] for m in [*pre.to_score, *pre.recoverable]]
    expected_hashes = {
        m["identity_key"]: {
            build_score_ctx(config, m, m["user_text"], tag)["request_hash"]
            for tag in ("score-1", "score-2")}
        for m in [*pre.to_score, *pre.recoverable]}
    analysis_rows = []
    if entry_ids:
        ph = ",".join("?" * len(entry_ids))
        for k, eid, s1, s2, tier, rids in conn.execute(
                f"SELECT e.identity_key, a.entry_id, a.score_1, a.score_2,"
                f" e.source_tier, a.receipt_ids FROM analysis a JOIN entry e"
                f" ON e.id=a.entry_id WHERE a.entry_id IN ({ph})"
                " AND a.prompt_version=? AND a.model=?"
                " AND a.score_1 IS NOT NULL AND a.score_2 IS NOT NULL",
                [*entry_ids, config.prompts.score.version,
                 config.budget.default_model]).fetchall():
            try:
                rid_list = json.loads(rids or "[]")
            except ValueError:
                continue
            if not rid_list:
                continue
            qmarks = ",".join("?" * len(rid_list))
            got = {r[0] for r in conn.execute(
                f"SELECT request_hash FROM receipt WHERE id IN ({qmarks})",
                rid_list)}
            if got == expected_hashes.get(k):
                analysis_rows.append(
                    {"identity_key": k, "entry_id": eid, "score_1": s1,
                     "score_2": s2, "source_tier": tier})
    if not analysis_rows:
        if skipped_pay:
            return 4                       # 留待解除后继续(不落 failed)
        if "unknown" in statuses or "retryable" in statuses:
            return 4                       # 可重试失败:保存进度,名额由
                                           # ledger 跨运行持有,下轮续接
                                           # (R2:failed 不自动恢复,提前落
                                           # failed 会冻结重试承诺)
        if "rejected" in statuses:
            return 4                       # 环境性闸门拒(预算/窗口):非
                                           # 内容失败,不落 E6 不触发两期通知
        if pre.to_score or pre.recoverable:
            _fail_issue(conn, issue_date, "E6.all_failed",
                        send=notify_send or _log_sender)
            return 3
        return 4                           # 全被排除/占用:转人工

    result = decide_selection(analysis_rows, config.selection.thresholds,
                              overrides)
    apply_selection(conn, issue_date, result)

    member_by_key = {m["identity_key"]: m for m in manifest}
    summaries: dict[str, dict] = {}
    for v in result.selected:
        out = understand_entry(conn, config, member_by_key[v.identity_key],
                               issue_date=issue_date, transport=transport,
                               now=now)
        if out.status == "completed":      # gate:pay_paused 拒=无副作用
            summaries[v.identity_key] = {
                "title_zh": out.title_zh, "summary": out.summary,
                "reason": out.reason, "tags": list(out.tags)}
        elif out.fail_reason and out.fail_reason.startswith("gate:pay_paused"):
            skipped_pay = True

    final_members = []
    selected_keys = set()
    for v in result.selected:
        selected_keys.add(v.identity_key)
        final_members.append({**member_by_key[v.identity_key],
                              "display_score": v.display_score,
                              "force_included": v.force_included,
                              "score_done": True,
                              "has_summary": v.identity_key in summaries})
    for m in manifest:      # force_include 无评分→就绪判据须见(转人工)
        if overrides.get(m["identity_key"]) == "force_include" \
                and m["identity_key"] not in selected_keys:
            final_members.append({**m, "display_score": 0,
                                  "force_included": True,
                                  "score_done": False, "has_summary": False})

    fsr = compute_final_set(final_members, overrides=overrides,
                            max_entries=config.selection.max_entries)
    if fsr.paused_reason:
        logger.error("stage=run event=assembly_paused issue=%s reason=%s",
                     issue_date, fsr.paused_reason)
        return 4
    if fsr.zero_qualified:
        if skipped_pay:
            return 4
        _fail_issue(conn, issue_date, "zero_qualified",
                        send=notify_send or _log_sender)
        return 3

    try:
        draft = assemble_issue(config, issue_date, fsr.final, summaries,
                               issue_cost_snapshot(conn, issue_date))
        path = ctx.workdir / ctx.digest_dir / f"{issue_date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        write_draft(conn, draft, path)
        # 清算口径=最终产物成员(交界 B-缝B):与恢复路径 entry_ids 口径
        # 一致——组装剔除的 safety_excluded 成员不进产物,不得置 used
        res = publish_issue(conn, issue_date, ctx,
                            final_keys=[m["identity_key"] for m in fsr.final
                                        if m["identity_key"]
                                        not in draft.safety_excluded])
    except (AssemblyPaused, ManualIntervention) as exc:
        logger.error("stage=run event=manual_intervention issue=%s"
                     " message=%s", issue_date, exc)
        notify_event(conn, "E8", issue_date, f"{issue_date} 转人工:{exc}",
                     send=notify_send or _log_sender)
        return 4
    if res.status != "published":
        notify_event(conn, "E8", issue_date,
                     f"{issue_date} 发布未确认({res.status}),转人工",
                     send=notify_send or _log_sender)
        return 4
    return 0


# ---------- 恢复与主流程 ----------

def _recover_issue(conn: sqlite3.Connection, config: Config,
                   ctx: PublishContext, issue_date: str, kind: str, *,
                   paid_allowed: bool, transport, now: datetime,
                   notify_send: Callable[[str, str], str] | None = None
                   ) -> int:
    """期内顺序:submitted 只读线上确认→draft 发布恢复→生成中续跑
    (单期恢复消费恢复预算;单窗口单步由 recover_issue 保证)。"""
    if kind == "generating":
        return _generate_issue(conn, config, issue_date, ctx,
                               paid_allowed=paid_allowed, transport=transport,
                               now=now, notify_send=notify_send)
    if kind == "submitted":
        out = recover_issue(conn, issue_date, ctx)   # W4 只读,零费用
        return 0 if out.status == "published" else 4

    out = recover_issue(conn, issue_date, ctx)       # W2/W3 单步
    status = conn.execute("SELECT status FROM digest_issue WHERE"
                          " issue_date=?", (issue_date,)).fetchone()[0]
    if status == "submitted":                        # W3 刚补记→只读确认
        out2 = recover_issue(conn, issue_date, ctx)
        return 0 if out2.status == "published" else 4
    res = publish_issue(conn, issue_date, ctx,
                        final_keys=_final_keys_from_entry_ids(conn, issue_date))
    return 0 if res.status == "published" else 4


def run_once(conn: sqlite3.Connection, config: Config, *, upstream_path: str,
             publish_ctx: PublishContext, transport=None,
             now: datetime | None = None, today: str | None = None,
             recover_budget_s: float = RECOVER_BUDGET_S,
             monotonic: Callable[[], float] | None = None,
             notify_send: Callable[[str, str], str] | None = None,
             events: Callable[[str], None] | None = None,
             snapshot_dir: "Path | None" = None) -> int:
    """一次完整运行(编排;main() 为其 CLI 装配薄层)。返回聚合退出码。"""
    now = now or datetime.now(timezone.utc)
    today = today or _shanghai_today(now)
    monotonic = monotonic or time.monotonic
    events = events or (lambda msg: None)
    codes: list[int] = []
    touched: set[str] = set()

    try:
        check_prompt_fits(config)                    # E1:拒启动不出网
    except (ConfigError, TokenizerUnavailable) as exc:
        logger.error("stage=run event=E1.config message=%s", exc)
        notify_event(conn, "E1.config", today, f"E1 配置错误:{exc}",
                     send=notify_send or _log_sender)
        return 2
    paid_allowed = _read_pay_paused(conn) == "0"    # 键缺失同拒新增
    if not paid_allowed:
        logger.warning("stage=run event=pay_paused 新增付费部分跳过,"
                       "只读/复用/结算照常")

    dirty = check_claim_invariant(conn)              # 启动校验:报告不修复
    if dirty:
        logger.error("stage=run event=claim_invariant_dirty keys=%s", dirty)

    # 先恢复存量(issue_date 升序;预算尽=保存状态继续新期)
    t0 = monotonic()
    for issue_date, kind in _open_issues(conn):
        if monotonic() - t0 >= recover_budget_s:
            logger.warning("stage=run event=recover_budget_exhausted"
                           " issue=%s 留待下次", issue_date)
            break
        freeze_row = conn.execute(
            "SELECT paused, frozen_utc FROM issue_freeze WHERE issue_date=?",
            (issue_date,)).fetchone()
        if freeze_row and freeze_row[0]:
            events(f"phase:skip_paused:{issue_date}")   # 零动作
            continue
        if kind != "submitted" and freeze_row \
                and not _auto_eligible(freeze_row[1], today):
            events(f"phase:expired:{issue_date}")       # 移出自动清单
            notify_event(conn, "auto_expire", issue_date,
                         f"{issue_date} 自动恢复到期(frozen_utc="
                         f"{freeze_row[1]})仍非终态,转人工",
                         send=notify_send or _log_sender)
            codes.append(4)
            continue
        events(f"phase:recover:{issue_date}")
        touched.add(issue_date)
        try:
            codes.append(_recover_issue(conn, config, publish_ctx, issue_date,
                                        kind, paid_allowed=paid_allowed,
                                        transport=transport, now=now,
                                        notify_send=notify_send))
        except ManualIntervention as exc:
            logger.error("stage=run event=manual_intervention issue=%s"
                         " message=%s", issue_date, exc)
            notify_event(conn, "E8", issue_date, f"{issue_date} 转人工:{exc}",
                         send=notify_send or _log_sender)
            codes.append(4)

    # 当天新期(已冻结/已 failed 的期号不重复处理;failed 不自动重跑)
    freeze_row = conn.execute(
        "SELECT paused FROM issue_freeze WHERE issue_date=?", (today,)).fetchone()
    has_row = conn.execute(
        "SELECT 1 FROM digest_issue WHERE issue_date=?", (today,)).fetchone()
    if freeze_row and freeze_row[0]:
        logger.warning("stage=run event=W1 当天期已暂停,不生成:%s", today)
        notify_event(conn, "W1", today,
                     f"{today} 当天期已被暂停,跳过生成(人工处理)",
                     send=notify_send or _log_sender)
        codes.append(4)
    elif freeze_row or has_row:
        logger.info("stage=run event=new_issue_skipped issue=%s"
                    " (已处理/failed)", today)
    else:
        events(f"phase:new:{today}")
        touched.add(today)
        try:
            collect_once(conn, upstream_path, config, today, now,
                         snapshot_dir=snapshot_dir)
            codes.append(_generate_issue(conn, config, today, publish_ctx,
                                         paid_allowed=paid_allowed,
                                         transport=transport, now=now,
                                         notify_send=notify_send))
        except ManualIntervention as exc:
            logger.error("stage=run event=manual_intervention issue=%s"
                         " message=%s", today, exc)
            notify_event(conn, "E8", today, f"{today} 转人工:{exc}",
                         send=notify_send or _log_sender)
            codes.append(4)
        except CollectError as exc:
            logger.error("stage=run event=E2 issue=%s message=%s",
                         today, exc)
            _fail_issue(conn, today, "E2.upstream",
                        send=notify_send or _log_sender)
            codes.append(3)

    # 月度预警(¥40 阈值,同月一封;规则 7):未决保守口径
    warn_at = getattr(config.budget, "warn_monthly_micro_cny", 0) or 0
    if warn_at > 0:
        _label, month_start, month_end = _month_window(now)
        month_used, _issue = _money_used(
            conn, start_utc=month_start, end_utc=month_end, issue_date=None)
        if month_used >= warn_at:
            notify_monthly(
                conn, _label,
                f"本月模型花费已达 ¥{month_used / 1e6:.2f}"
                f"(阈值 ¥{warn_at / 1e6:.2f}),请核对用量",
                send=notify_send or _log_sender)

    # 汇总记账:核清后过期期巡检(提示不自动更新)
    for s in stale_cost_issues(conn):
        logger.warning("stage=run event=stale_cost issue=%s row=%.4f"
                       " snapshot=%.4f(人工走纠错提交)",
                       s["issue_date"], s["row_cost_cny"],
                       s["snapshot_cost_cny"])

    exit_code = _pick_exit(codes)
    stamp = _now_str()
    with conn:                                        # 收尾:有行者写运行事实
        for issue_date in sorted(touched):
            conn.execute(
                "UPDATE digest_issue SET last_exit=?, last_run_utc=?"
                " WHERE issue_date=?", (exit_code, stamp, issue_date))
    logger.info("stage=run event=run_end exit=%d codes=%s", exit_code, codes)
    return exit_code


# ---------- failed 人工重跑/放弃(显式命令;调度不触碰 failed) ----------

def rerun_issue(conn: sqlite3.Connection, config: Config, issue_date: str, *,
                publish_ctx: PublishContext, transport=None,
                now: datetime | None = None) -> int:
    """failed 期人工重跑=续跑语义:冻结在→读 manifest,回执按身份复用,
    未完成阶段继续(不重新 collect;人工命令不受自动截止限制)。"""
    now = now or datetime.now(timezone.utc)
    row = conn.execute("SELECT status FROM digest_issue WHERE issue_date=?",
                       (issue_date,)).fetchone()
    frozen = conn.execute(
        "SELECT 1 FROM issue_freeze WHERE issue_date=?", (issue_date,)
    ).fetchone()
    if row is None or row[0] != "failed" or frozen is None:
        raise ManualIntervention(
            f"rerun 前置失败:{issue_date} 须为 failed 且冻结行在")
    code = _generate_issue(conn, config, issue_date, publish_ctx,
                           paid_allowed=_read_pay_paused(conn) == "0",
                           transport=transport, now=now)
    with conn:
        conn.execute("UPDATE digest_issue SET last_exit=?, last_run_utc=?"
                     " WHERE issue_date=?", (code, _now_str(), issue_date))
    return code


def abandon_issue(conn: sqlite3.Connection, issue_date: str, *,
                  reason: str) -> None:
    """放弃失败期(人工核对后):释放占用(claim 清/selected 回 scored,
    used 不动)+留痕;digest_issue 保持 failed(历史)。"""
    release_abandoned_issue(conn, issue_date)
    logger.info("stage=run event=abandon issue=%s reason=%s", issue_date,
                reason)
    with conn:
        conn.execute("UPDATE digest_issue SET last_run_utc=?"
                     " WHERE issue_date=?", (_now_str(), issue_date))


def _upstream_path_from_env(root: Path) -> str:
    """Task 25 部署接线:上游 topic-digest 库路径经 NANMU_UPSTREAM_DB
    注入。不用 symlink 指向真实库——SQLite 按打开路径推 -wal/-shm 侧车
    名,symlink 会让只读连接找不到真实 WAL(读到旧快照丢当日数据)。
    未设=现状 root/topic-digest.db(本地替身测试零改动)。"""
    import os
    return os.environ.get("NANMU_UPSTREAM_DB",
                          str(root / "topic-digest.db"))


def _publish_ctx_from_env(root: Path) -> PublishContext:
    """部署接线(Task 25):发布上下文经环境变量注入,服务器路径不写死
    在代码——NANMU_PUBLISH_REMOTE(专用副本远端 git URL)、
    NANMU_SITE_BASE(线上基址,构造期页 URL)、NANMU_RELEASE_TXT
    (部署 SHA 文件路径,如 current/dist/release.txt)。未设=本地替身
    现状(空远端/无部署证据/URL 不确认),既有替身测试零改动;
    release.txt 读不到=证据不足返回 None(URL/SHA 误判语义由
    publish 层消费,此处不抛)。"""
    import os
    import urllib.request

    remote = os.environ.get("NANMU_PUBLISH_REMOTE", "")
    site_base = os.environ.get("NANMU_SITE_BASE", "")
    release_txt = os.environ.get("NANMU_RELEASE_TXT", "")

    def _sha() -> str | None:
        if not release_txt:
            return None
        try:
            return Path(release_txt).read_text(encoding="utf-8").strip()
        except OSError:
            return None                     # 部署切换窗口/路径错=证据不足

    def _ok(url: str) -> bool:
        if not site_base:
            return False
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return 200 <= resp.status < 300
        except OSError:
            return False

    return PublishContext(workdir=root / "site-work", remote_url=remote,
                          branch="main", site_base=site_base,
                          fetch_release_sha=_sha, fetch_url_ok=_ok)


def main(argv: list[str] | None = None) -> int:
    """CLI 装配薄层(锁→config→DB→PublishContext→run_once);单实例
    flock 由本层持有(Windows msvcrt/POSIX fcntl 各取其一)。
    PublishContext 的真实远端/工作副本装配属 Task 25(部署);M1 骨架
    remote_url 留空;真实部署经环境变量注入(NANMU_PUBLISH_REMOTE 等,
    见 _publish_ctx_from_env)。"""
    import argparse

    from nanmu_engine.config import load_config
    from nanmu_engine.db import connect_db, migrate

    try:
        import msvcrt

        def _acquire(lock_file):
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
    except ImportError:                      # POSIX 部署目标(Task 25)
        import fcntl

        def _acquire(lock_file):
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    parser = argparse.ArgumentParser(prog="nanmu-run")
    parser.add_argument("--root", default=".", help="engine 根目录")
    args = parser.parse_args(argv)
    root = Path(args.root)

    lock_path = root / "run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(lock_path, "a")
    try:
        _acquire(lock)
    except OSError:
        logger.error("stage=run event=lock_busy 另一实例运行中,退出")
        return 1

    try:
        try:
            config = load_config(root)
        except ConfigError as exc:
            logger.error("stage=run event=E1.config message=%s", exc)
            return 2
        conn = connect_db(str(root / "engine.db"))
        migrate(conn)
        ctx = _publish_ctx_from_env(root)
        return run_once(conn, config,
                        upstream_path=_upstream_path_from_env(root),
                        publish_ctx=ctx, snapshot_dir=root / "upstream-snap")
    finally:
        lock.close()


if __name__ == "__main__":                   # systemd timer 挂载点
    raise SystemExit(main())
