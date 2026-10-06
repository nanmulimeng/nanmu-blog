"""入选判断与 claim 占用协议(content-editing §3 规则 4/6/7/9)。

判定与写入分离:decide_selection/compute_final_set 是纯函数(评分与
入选分离——同双分随当期门槛/override 重新判定,跨期可复用);claim
协议的持久化操作各自单事务:selected 同事务写 claim+analysis.selected;
发布终态统一清算(进产物 used/未进 rejected,均清 claim);放弃回
scored(used 不动);启动校验暴露 selected 而 claim 空的脏行。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MemberVerdict:
    identity_key: str
    entry_id: int
    display_score: int                 # floor((score_1+score_2)/2)
    selected: bool
    force_included: bool = False


@dataclass(frozen=True)
class SelectionResult:
    selected: list[MemberVerdict] = field(default_factory=list)
    rejected: list[MemberVerdict] = field(default_factory=list)


def decide_selection(analysis_rows: list[dict], thresholds: dict[str, int],
                     override: dict[str, str]) -> SelectionResult:
    """入选判定(规则 4):双分齐且 floor((s1+s2)/2) 过源 tier 门槛 →
    selected;force_include 越过门槛但标记 force_included(不绕过来源/
    安全/预算——那些约束在闸门与就绪判据里);其余 rejected(不写 claim,
    下期同分可重新判定)。"""
    selected, rejected = [], []
    for row in analysis_rows:
        display = (row["score_1"] + row["score_2"]) // 2
        force = override.get(row["identity_key"]) == "force_include"
        tier = row.get("source_tier", "T2")
        passes = display >= thresholds.get(tier, thresholds["T2"])
        verdict = MemberVerdict(identity_key=row["identity_key"],
                                entry_id=row["entry_id"],
                                display_score=display,
                                selected=passes or force,
                                force_included=force)
        (selected if verdict.selected else rejected).append(verdict)
    return SelectionResult(selected, rejected)


# ---------- claim 协议持久化(规则 7) ----------

def apply_selection(conn: sqlite3.Connection, issue_date: str,
                    result: SelectionResult) -> None:
    """入选判断通过 → entry.status='selected' + claim_issue=本期,与
    analysis.selected 回写同一事务;首次落选 → 'rejected',不写 claim。"""
    with conn:
        for v in result.selected:
            conn.execute(
                "UPDATE entry SET status='selected', claim_issue=?"
                " WHERE identity_key=?", (issue_date, v.identity_key))
            conn.execute(
                "UPDATE analysis SET selected=1 WHERE entry_id=?",
                (v.entry_id,))
        for v in result.rejected:
            conn.execute(
                "UPDATE entry SET status='rejected', claim_issue=NULL"
                " WHERE identity_key=?", (v.identity_key,))


def settle_published(conn: sqlite3.Connection, issue_date: str,
                     final_identity_keys: list[str]) -> None:
    """published 终态统一清算(单事务):本期 claim 的全部 entry——进最终
   产物 → 'used'+清 claim;未进(裁剪/剔除)→ 'rejected'+清 claim。
    混合事实不允许存在:rejected 不持旧 claim。"""
    with conn:
        _settle_published_sql(conn, issue_date, final_identity_keys)


def _settle_published_sql(conn: sqlite3.Connection, issue_date: str,
                          final_identity_keys: list[str]) -> None:
    """settle 的事务体(供发布单元在同一事务内与 published 状态推进
    合并执行——publish-withdraw §3 规则 2 表)。"""
    final = set(final_identity_keys)
    rows = conn.execute(
        "SELECT identity_key FROM entry WHERE claim_issue=?",
        (issue_date,)).fetchall()
    for (key,) in rows:
        if key in final:
            conn.execute(
                "UPDATE entry SET status='used', claim_issue=NULL"
                " WHERE identity_key=?", (key,))
        else:
            conn.execute(
                "UPDATE entry SET status='rejected', claim_issue=NULL"
                " WHERE identity_key=?", (key,))


def release_abandoned_issue(conn: sqlite3.Connection, issue_date: str) -> None:
    """放弃本期(异常暂离/人工接手前的回收):claim 清、selected 回
    scored(评分成果保留,下期可重新判定);used 不动(历史产物事实)。"""
    with conn:
        conn.execute(
            "UPDATE entry SET status='scored', claim_issue=NULL"
            " WHERE claim_issue=? AND status='selected'", (issue_date,))


def check_claim_invariant(conn: sqlite3.Connection) -> list[str]:
    """启动校验(规则 7 末行):selected ⇒ claim 非空。返回违例
    identity_key 清单(由运行序在启动时报告,不静默修复)。"""
    rows = conn.execute(
        "SELECT identity_key FROM entry WHERE status='selected'"
        " AND (claim_issue IS NULL OR claim_issue='')").fetchall()
    return [r[0] for r in rows]


# ---------- 最终产物集合与就绪判据(规则 6/9) ----------

@dataclass(frozen=True)
class FinalSetResult:
    final: list[dict]                          # 最终产物成员
    excluded: dict[str, str]                   # identity_key → 剔除原因
    paused_reason: str | None                  # force_member_incomplete / force_over_limit
    zero_qualified: bool                       # 最终集合空(不产 draft,验收 9)


def compute_final_set(members: list[dict], *, overrides: dict[str, str],
                      max_entries: int = 15) -> FinalSetResult:
    """失败隔离与数量规则(规则 6):普通项缺摘要 → 剔除该条不挂整期;
    强制项任一未完成 → 组装暂停转人工(不绕过任何约束);F>15 → 暂停;
    F≤15 → 普通按展示分排序最多取 15−F;最终集合空 → zero_qualified。"""
    excluded: dict[str, str] = {}
    force = [m for m in members
             if overrides.get(m["identity_key"]) == "force_include"
             or m.get("force_included")]
    for m in force:
        if not m.get("has_summary") or not m.get("score_done"):
            return FinalSetResult([], {}, "force_member_incomplete", False)
    if len(force) > max_entries:
        return FinalSetResult([], {}, "force_over_limit", False)

    quota = max_entries - len(force)
    normals = [m for m in members if m not in force]
    ready, dropped = [], []
    for m in normals:
        if not m.get("has_summary"):
            excluded[m["identity_key"]] = "summary_failed"
        else:
            ready.append(m)
    ready.sort(key=lambda m: (-m.get("display_score", 0), m["identity_key"]))
    kept = ready[:quota]
    for m in ready[quota:]:
        excluded[m["identity_key"]] = "count_capped"
    final = force + kept
    return FinalSetResult(final, excluded, None, not final)
