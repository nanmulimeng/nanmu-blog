"""运维命令实现:restore-backup 五步序列、pause/unpause、status 聚合。

restore-backup(scheduling-ops §3 规则 9,第二轮核验修正):**先在待启用
副本内置 pay_paused=1 并读回校验、后原子切换活动库**——不变量"活动库
完成切换 ⇔ 其内 pay_paused=1 已先持久化",消除恢复操作自身的中断窗口
("先恢复后置位"顺序被禁止:两步之间崩溃=旧库已生效而标志未写)。恢复
旧库会丢失备份之后的回执事实,同身份请求将按"从未发起"重发=重复付费,
故切换前必须先落付费暂停。全程持有与常规运行相同的单实例锁(run.lock,
由命令层持有);闸门读法=pay_paused 仅显式 0 放行,键缺失(裸恢复/库
异常)同拒(status 输出提示核对)。

status(§3 规则 8)=只读聚合五组事实,无新存储;输出字段与 digest-design
§3.5 样例对应(措辞实现可微调)。
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from nanmu_engine.db import connect_db

logger = logging.getLogger(__name__)

_STEPS = ("copy", "set_flag", "verify", "checkpoint", "switch")


class OpsCommandError(Exception):
    """命令参数错(期不存在等);消息附可用期清单(§4 非法输入处置)。"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _shanghai_today() -> str:
    return (datetime.now(timezone.utc)
            .astimezone(timezone(timedelta(hours=8))).date().isoformat())


def _require_freeze(conn: sqlite3.Connection, issue_date: str) -> None:
    """期前置:freeze 行须在;不在→拒绝并列可用期。"""
    row = conn.execute("SELECT 1 FROM issue_freeze WHERE issue_date=?",
                       (issue_date,)).fetchone()
    if row is None:
        avail = [d for (d,) in conn.execute(
            "SELECT issue_date FROM issue_freeze ORDER BY issue_date")]
        raise OpsCommandError(
            f"期不存在:{issue_date}(可用期:{', '.join(avail) or '无'})")


# ---------- 规则 4:暂停与解除(撤回序列同一实现) ----------

def pause_issue(conn: sqlite3.Connection, issue_date: str, *,
                reason: str) -> None:
    """置位=issue_freeze.paused=1+reason+utc(UPDATE 单事务,命令带原因)。
    效果=调度跳过该期一切自动动作;可叠加任何冻结后状态。"""
    _require_freeze(conn, issue_date)
    with conn:
        conn.execute(
            "UPDATE issue_freeze SET paused=1, paused_reason=?, paused_utc=?"
            " WHERE issue_date=?", (reason, _utc_now(), issue_date))
    logger.info("stage=ops event=pause issue=%s reason=%s", issue_date,
                reason)


def unpause_issue(conn: sqlite3.Connection, issue_date: str) -> None:
    """解除只恢复调度可见性:不改状态、不触发发布、不撤回撤回。"""
    _require_freeze(conn, issue_date)
    with conn:
        conn.execute("UPDATE issue_freeze SET paused=0 WHERE issue_date=?",
                     (issue_date,))
    logger.info("stage=ops event=unpause issue=%s", issue_date)


# ---------- 规则 9:备份恢复五步(先持久化暂停、后切换) ----------

def restore_backup(backup_path: str | Path, live_path: str | Path, *,
                   after_step: Callable[[str], None] | None = None
                   ) -> dict:
    """五步序列(§3 规则 9 表,逐字)。调用方须持有与常规运行相同的
    单实例锁(恢复期间无运行实例并发写活动库)。

    ① 备份恢复到待启用副本路径(不动活动库)→②副本置 pay_paused=1
    (事务+wal_checkpoint(FULL)+关闭)→③**读回校验**:全新连接重开
    副本,key 存在且='1',失败中止不切换→④活动库 wal_checkpoint
    (TRUNCATE)(已提交帧并入主文件,清边车不再丢数据)→原子切换
    os.replace(副本替换活动库)→⑤返回核对清单。after_step=每步完成
    后的回调(崩溃注入点:该步之后恢复序列不再执行)。

    各步后崩溃:①②③④(checkpoint)→活动库未动,可重试(重试①
    覆盖旧副本,幂等);切换→新活动库已含标志。不变量恒成立:活动库
    被备份替换 ⇔ 其内 pay_paused=1 已先持久化。
    """
    backup = Path(backup_path)
    live = Path(live_path)
    pending = Path(str(live) + ".restore-pending")
    hook = after_step or (lambda step: None)

    # ① 恢复到待启用副本(覆盖上次中断遗留的副本=重试幂等)
    shutil.copy2(backup, pending)
    hook("copy")

    # ② 在副本上置 pay_paused=1(checkpoint 强制 WAL 落盘再关闭)
    flag_conn = connect_db(str(pending))
    try:
        with flag_conn:
            flag_conn.execute(
                "INSERT INTO engine_meta (key, value, updated_utc)"
                " VALUES ('pay_paused', '1', ?)"
                " ON CONFLICT(key) DO UPDATE SET value='1',"
                " updated_utc=excluded.updated_utc", (_utc_now(),))
        flag_conn.execute("PRAGMA wal_checkpoint(FULL)")
    finally:
        flag_conn.close()
    hook("set_flag")

    # ③ 读回校验:全新连接(不经置位连接的任何缓存),失败中止不切换
    check = sqlite3.connect(str(pending))
    try:
        row = check.execute(
            "SELECT value FROM engine_meta WHERE key='pay_paused'"
        ).fetchone()
    finally:
        check.close()
    if row is None or row[0] != "1":
        raise OpsCommandError(
            f"读回校验失败:副本 pay_paused={'缺失' if row is None else row[0]}"
            "(预期 1),中止切换,活动库未动")
    hook("verify")

    # ④-1 活动库 WAL 安全 checkpoint(审计 P1-1):硬杀现场已提交回执
    # 可驻留 -wal(未 checkpoint 帧)。删除边车不能作为 checkpoint 的
    # 替代——先 TRUNCATE checkpoint 把已提交帧并入主文件,再清边车再
    # 切换;此后"checkpoint 后、切换前"中断=旧库主文件自持全部已提交
    # 事实。活动库打不开/合并受阻=中止不切换(旧库连同边车原样保留,
    # 留人工处理,不得在完整性未证时切走旧账本)
    if live.exists():
        live_conn = sqlite3.connect(str(live))
        try:
            row = live_conn.execute(
                "PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if row is None or row[0] != 0:
                raise OpsCommandError(
                    f"活动库 WAL checkpoint 受阻(busy={row})(已提交数据"
                    f"完整性未证,中止切换,活动库未动)")
        except sqlite3.Error as exc:
            raise OpsCommandError(
                f"活动库 WAL checkpoint 失败(中止切换,活动库未动):{exc}"
            ) from exc
        finally:
            live_conn.close()
    hook("checkpoint")

    # ④-2 原子切换(Windows os.replace=MoveFileEx REPLACE_EXISTING)。
    # 先清残留 -wal/-shm:活动库侧已 checkpoint(TRUNCATE),帧已并入主
    # 文件,清理不再丢已提交数据;硬杀残留边车若不清会在重开时回放到
    # 恢复库上,得到新旧混合态(极端情形旧库 pay_paused=0 页面复活,
    # 击穿五步不变量);副本侧经 wal_checkpoint(FULL)+close,不带边车
    for sidecar in (f"{live}-wal", f"{live}-shm",
                    f"{pending}-wal", f"{pending}-shm"):
        try:
            os.remove(sidecar)
        except FileNotFoundError:
            pass
    os.replace(pending, live)
    hook("switch")

    # ⑤ 核对清单
    checklist = [
        "新活动库已启用且 pay_paused=1(付费暂停生效,闸门拒绝一切新增)",
        "核对恢复点之后的供应商调用与账单(丢失的回执按未发起重发=重复付费)",
        "核对上游库/站点不受影响(git 是 site 唯一真相源;上游为他人资产)",
        "确认无需补录或已修正预算后,人工显式置 pay_paused=0 解除",
    ]
    for item in checklist:
        logger.info("stage=ops event=restore_checklist item=%s", item)
    return {"live": str(live), "checklist": checklist}


# ---------- 规则 8:status 只读聚合(五组事实;§3.5 样例) ----------

def _entry_counts(conn: sqlite3.Connection, manifest_json: str | None,
                  frozen: int) -> dict:
    """②条目计数:manifest entry_count vs entry 现状(scored/selected/used)。"""
    counts = {"frozen": frozen, "scored": 0, "selected": 0, "used": 0}
    if not manifest_json:
        return counts
    ids = [m["entry_id"] for m in json.loads(manifest_json)
           if isinstance(m, dict) and "entry_id" in m]
    for id_ in ids:
        row = conn.execute("SELECT status FROM entry WHERE id=?",
                           (id_,)).fetchone()
        if row and row[0] in counts:
            counts[row[0]] += 1
    return counts


def _attempt_facts(conn: sqlite3.Connection, issue_date: str) -> dict:
    """③attempt 结算与未决:settled Σ/未核清计数+保守预占(未核清行的
    reserved;actual 已核清的不重复计入)。"""
    settled_count, settled_micro = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(actual_micro_cny), 0)"
        " FROM receipt_attempt WHERE issue_date=? AND actual_micro_cny"
        " IS NOT NULL", (issue_date,)).fetchone()
    unsettled_count, reserved_micro = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(reserved_micro_cny), 0)"
        " FROM receipt_attempt WHERE issue_date=? AND actual_micro_cny"
        " IS NULL", (issue_date,)).fetchone()
    return {"settled_count": settled_count,
            "settled_cny": settled_micro / 1_000_000,
            "unsettled_count": unsettled_count,
            "reserved_cny": reserved_micro / 1_000_000}


def _next_hint(status_text: str | None, paused: bool,
               withdrawn: bool) -> str:
    """⑤下一步建议(§3.5 样例措辞,实现可微调)。"""
    if status_text is None:
        return "无该期记录"
    if paused and status_text != "published" and status_text != "failed":
        return "暂停中:解除后恢复调度可见性(不改状态不触发发布)"
    return {
        "generating": "生成中:等待下次调度续跑(冻结在,回执按身份复用)",
        "draft": "发布恢复:单步推进(push→线上证据链)",
        "submitted": "等待线上确认(只读,零费用)",
        "failed": "人工显式重跑(候选已冻结、已收响应复用,不重复付费);不自动重试",
        "published": ("已撤回:重新上线走恢复经确认的内容版本"
                      if withdrawn else "已完成"),
    }.get(status_text, "未知状态")


def _warnings(conn: sqlite3.Connection) -> list[str]:
    """pay_paused 异常态提示:键缺失=疑似裸恢复(§3 规则 9 闸门读法);
    =1=正常置位态,附核对提醒(解除协议=人工显式置 0)。"""
    row = conn.execute(
        "SELECT value FROM engine_meta WHERE key='pay_paused'").fetchone()
    if row is None:
        return ["活动库无 pay_paused 键(疑似绕过 restore-backup 的裸恢复或"
                "库损坏):闸门拒绝新增付费,请核对恢复操作与账单"]
    if row[0] != "0":
        return ["pay_paused=1(付费暂停生效):核对恢复点之后的调用与账单,"
                "确认后显式置 0 解除"]
    return []


def _issue_view(conn: sqlite3.Connection, issue_date: str) -> dict:
    """单期五组事实(①状态与叠加②条目③attempt④最近 run⑤建议)。"""
    freeze = conn.execute(
        "SELECT entry_count, manifest_json, paused, paused_reason"
        " FROM issue_freeze WHERE issue_date=?", (issue_date,)).fetchone()
    digest = conn.execute(
        "SELECT status, fail_reason, last_exit, last_run_utc, withdrawn_utc,"
        " withdraw_commit FROM digest_issue WHERE issue_date=?",
        (issue_date,)).fetchone()

    paused = bool(freeze and freeze[2])
    if digest:
        status_text = digest[0]
    elif freeze:
        status_text = "generating"              # 冻结在而无行
    else:
        status_text = None
    return {
        "issue_date": issue_date,
        "status": status_text,                  # ①期状态与叠加
        "paused": paused,
        "paused_reason": freeze[3] if freeze else None,
        "withdrawn": bool(digest and digest[4]),
        "withdraw_commit": digest[5] if digest else None,
        "fail_reason": digest[1] if digest else None,
        "entries": _entry_counts(conn, freeze[1] if freeze else None,
                                 freeze[0] if freeze else 0),
        "attempts": _attempt_facts(conn, issue_date),
        "last_run": ({"exit": digest[2], "utc": digest[3]}
                     if digest else None),       # ④最近 run
        "next": _next_hint(status_text, paused,
                           bool(digest and digest[4])),   # ⑤建议
    }


def status(conn: sqlite3.Connection, issue_date: str | None = None, *,
           today: str | None = None) -> dict:
    """只读聚合。issue_date 给定=该期五组事实;无参=全部未完成期+当日
    概览。warnings 恒含 pay_paused 异常态提示(键缺失=裸恢复)。"""
    warnings = _warnings(conn)
    if issue_date is not None:
        view = _issue_view(conn, issue_date)
        view["warnings"] = warnings
        return view

    open_issues = []
    status_by_date = dict(conn.execute(
        "SELECT issue_date, status FROM digest_issue"
        " WHERE status IN ('draft','submitted')").fetchall())
    terminal = {d for (d,) in conn.execute(
        "SELECT issue_date FROM digest_issue"
        " WHERE status IN ('published','failed')")}
    for (d, frozen_paused) in conn.execute(
            "SELECT issue_date, paused FROM issue_freeze"
            " ORDER BY issue_date"):
        if d in terminal:
            continue      # 终态期不进 open(failed 不自动重跑,published 完成)
        open_issues.append({"issue_date": d,
                            "status": status_by_date.pop(d, "generating"),
                            "paused": bool(frozen_paused)})
    for d, s in sorted(status_by_date.items()):   # 有行无 freeze(异常但可见)
        open_issues.append({"issue_date": d, "status": s, "paused": False})

    today = today or _shanghai_today()
    digest = conn.execute(
        "SELECT status FROM digest_issue WHERE issue_date=?",
        (today,)).fetchone()
    freeze = conn.execute(
        "SELECT 1 FROM issue_freeze WHERE issue_date=?", (today,)).fetchone()
    today_status = (digest[0] if digest
                    else ("generating" if freeze else None))
    return {"open": open_issues,
            "today": {"issue_date": today, "status": today_status},
            "warnings": warnings}


# ---------- 规则 11(model-calls §3):校准通道执行体(替身验证) ----------

CALIBRATION_SAMPLES = (
    {"title": "合成样本·甲", "content_text": "校准用最小合成材料。内容极短,"
     "仅构造完整请求结构。"},
    {"title": "合成样本·乙", "content_text": "第二条最小合成材料,与甲不同"
     "正文,验证同 prompt 下不同输入的计数稳定性。"},
    {"title": "合成样本·丙", "content_text": "第三条最小合成材料,含少量"
     "标点与数字 1234567890,覆盖常见字符分布。"},
    {"title": "真实短文样本", "content_text": "模型上下文窗口内的注意力分配"
     "机制决定了长文本中段信息容易被忽略;评测显示分词边界与提示词结构对"
     "实际消耗 token 数的影响不可忽略,校准必须用真实分布的正文验证。"},
)
"""阶段 B 固定样本:3 条最小合成材料+1 条真实短文(可复现;阶段 A 的
离线 90 条计数验证已完成于 token_count 模块)。"""


def _calibration_spent_micro(conn: sqlite3.Connection) -> int:
    """校准通道已批准预占累计微元合计(复核 P1,契约=model-calls §3
    规则 11:calibration.budget_micro_cny 限制"按预占值批准的调用量",
    不因结算回落到 actual——小额不自动保证实付不超)。"""
    return conn.execute(
        "SELECT COALESCE(SUM(a.reserved_micro_cny), 0) FROM receipt_attempt a"
        " JOIN receipt r ON r.id=a.receipt_id"
        " WHERE r.purpose='calibration'").fetchone()[0]


def calibrate(conn: sqlite3.Connection, config: Config, *, transport,
              samples=None, now: datetime | None = None) -> dict:
    """校准执行体(规则 11,替身验证;真实调用属 Task 26 授权范围)。

    每次校准调用走完整账本(authorize 预占→attempt→record_response 结算
    与对账),月预算与窗口限额照常适用,不设免检额度;单列
    calibration.budget_micro_cny 为预占合计上限,耗尽即中止不追加。
    判定:全部样本 usage.prompt_tokens ≤ 预占计数(计数×系数向上取整)
    →写生效记录(绑定配置指纹+系数);任一超出→record_response 对账已
    持久化置 pay_paused(规则 2 同一闸门),记录写失败态,人工上调系数
    后重新校准。同身份(calibration purpose+样本+系数)已有结算回执的
    样本直接复用账本结果,零网络零新增付费。
    """
    from nanmu_engine.llm import LLMRequest, call_llm, classify_failure
    from nanmu_engine.ledger import (_logical_key, _reserved_micro,
                                     authorize, can_retry,
                                     current_coefficient, recover_stale_pending,
                                     request_hash, write_calibration_record)
    from nanmu_engine.score import (_system_messages, _truncate_user)
    from nanmu_engine.token_count import count_request_tokens

    now = now or datetime.now(timezone.utc)
    samples = list(samples) if samples is not None \
        else [dict(s) for s in CALIBRATION_SAMPLES]
    model = config.budget.default_model
    coefficient = current_coefficient(conn)
    budget_micro = config.budget.calibration_budget_micro_cny
    results: list[dict] = []
    stopped: str | None = None

    for i, sample in enumerate(samples):
        try:
            user_text, token_count = _truncate_user(
                config, sample["title"], sample["content_text"],
                config.prompts.score.text)
        except Exception as exc:        # 计数不可得/标题超界 → 不出网
            logger.error("stage=calibrate event=count_failed sample=%d"
                         " message=%s", i, exc)
            return {"status": "tokenizer_unavailable", "passed": False,
                    "results": results}
        messages = _system_messages(config.prompts.score.text, user_text)
        ctx = {"provider": "deepseek", "endpoint": "/chat/completions",
               "purpose": "calibration", "model": model,
               "prompt_version": config.prompts.score.version,
               "system_text": config.prompts.score.text, "user_text": user_text,
               "max_tokens": config.budget.max_output_tokens,
               "thinking": config.budget.thinking,
               "response_format": "json_object" if config.budget.json_output
                                  else "text",
               # 系数入身份:人工上调系数后重校准=新请求身份(同系数重跑
               # 撞旧回执,复用判定零付费,防重复计费)
               "identity_key": f"calibration:coef-{coefficient}:sample-{i}",
               "content_hash": sample.get("content_hash", ""),
               "attemptTag": f"calibration-{i}"}
        rh = request_hash(ctx)
        logical_key = _logical_key("calibration", model, rh)   # 与账本写入同构

        # 交界 A1:replay 取最新成功 attempt(status='received' 且带
        # usage)——首发传输 unknown 后过窗补发结算的是 attempt_no=2,
        # 只认 attempt_no=1 会判"未复用"对已付费样本重复出网。
        # 复核 P1:usage_json 非空≠通过证据——失败回执也可带 usage
        # (record_failure 会写入),只是费用证据;replay 有效性条件与
        # 首次消费一致:仅成功(received)attempt 可作校准通过样本
        replay = conn.execute(
            "SELECT a.usage_json FROM receipt r JOIN receipt_attempt a"
            " ON a.receipt_id=r.id"
            " WHERE r.logical_key=? AND a.status='received'"
            " AND a.usage_json IS NOT NULL"
            " ORDER BY a.attempt_no DESC LIMIT 1", (logical_key,)).fetchone()
        if replay and replay[0]:
            prompt_tokens = json.loads(replay[0]).get("prompt_tokens")
            results.append({"sample": i, "prompt_tokens": prompt_tokens,
                            "reserved_count": math.ceil(
                                token_count * coefficient), "reused": True})
            continue

        reserved_micro = _reserved_micro(conn, config, model, token_count)
        spent = _calibration_spent_micro(conn)
        if spent + reserved_micro > budget_micro:
            logger.warning("stage=calibrate event=budget_exhausted"
                           " spent=%d next=%d budget=%d", spent,
                           reserved_micro, budget_micro)
            stopped = "budget_exhausted"
            break

        # 交界 A2:校准再发送同构 can_retry 三条件(§3 规则 3,与
        # score._attempt_side 同构)——unknown 30min 窗内等待而非重复
        # 出网;过窗走 unknown_retry 通道,attempt_origin 如实记录
        origin = "initial"
        prior = conn.execute(
            "SELECT id FROM receipt WHERE logical_key=?",
            (logical_key,)).fetchone()
        if prior is not None:
            recover_stale_pending(conn, config, logical_key, now)
            verdict = can_retry(conn, config, logical_key, now)
            if not verdict.allowed:
                stopped = (verdict.reason if verdict.reason in
                           ("unknown_wait", "attempt_in_flight")
                           else f"resend_{verdict.reason}")
                logger.info("stage=calibrate event=resend_blocked sample=%d"
                            " reason=%s", i, stopped)
                break
            origin = "retry" if verdict.channel == "normal" \
                else (verdict.channel or "initial")

        ref = authorize(conn, config, purpose="calibration", model=model,
                        request_hash=rh, identity_key=ctx["identity_key"],
                        token_count=token_count, issue_date=None,
                        origin=origin, now=now)
        if ref.status != "reserved":
            stopped = ref.reject_reason or "gate"
            logger.warning("stage=calibrate event=gate_rejected sample=%d"
                           " reason=%s", i, stopped)
            break

        request = LLMRequest(model=model, messages=messages,
                             max_tokens=ctx["max_tokens"],
                             purpose="calibration", request_hash=rh)
        try:
            result = call_llm(request, transport=transport)
            error_class, detail = classify_failure(result)
        except Exception as exc:
            from nanmu_engine.ledger import record_failure
            error_class, detail = classify_failure(exc)
            record_failure(conn, config, ref, error_class, detail)
            stopped = f"sample_failed:{error_class or 'unknown'}"
            break
        if error_class is not None:
            from nanmu_engine.ledger import record_failure
            record_failure(conn, config, ref, error_class, detail,
                           usage=result.usage)
            stopped = f"sample_failed:{error_class}"
            break

        from nanmu_engine.ledger import record_response
        record_response(conn, config, ref, result)   # 结算+对账(超→pause)
        prompt_tokens = (result.usage or {}).get("prompt_tokens")
        results.append({"sample": i, "prompt_tokens": prompt_tokens,
                        "reserved_count": math.ceil(
                            token_count * coefficient), "reused": False})

    any_over = any(r["prompt_tokens"] is not None
                   and r["prompt_tokens"] > r["reserved_count"]
                   for r in results)
    if any_over:
        # 对账已在 record_response 同事务持久化置 pay_paused(规则 2);
        # 此处写失败态记录,人工核对后上调系数再重新校准
        write_calibration_record(conn, config, coefficient=coefficient,
                                 results=results, passed=False)
        logger.error("stage=calibrate event=ratio_over counts=%s", results)
        return {"status": "failed", "passed": False, "results": results}
    if stopped:
        # unknown_wait 单列(交界 A2):等待语义非闸门拒——过窗后自动按
        # unknown_retry 通道续,调用方不据此升级为配置/预算故障
        status = stopped if stopped in ("budget_exhausted", "unknown_wait") \
            else f"gate_rejected:{stopped}"
        return {"status": status, "passed": False, "results": results}
    if any(r["prompt_tokens"] is None for r in results):
        # R3:缺 usage.prompt_tokens=未取得计量证据。"没有观察到超量"
        # 不等于"已取得通过证据"——校准是付费链路授权前置,证据不足
        # 不得 passed(回执未结算保留未决,人工排查后重校准)
        write_calibration_record(conn, config, coefficient=coefficient,
                                 results=results, passed=False)
        logger.error("stage=calibrate event=missing_usage results=%s",
                     results)
        return {"status": "missing_usage", "passed": False,
                "results": results}
    write_calibration_record(conn, config, coefficient=coefficient,
                             results=results, passed=True)
    logger.info("stage=calibrate event=passed coefficient=%s samples=%d",
                coefficient, len(results))
    return {"status": "passed", "passed": True, "results": results}
