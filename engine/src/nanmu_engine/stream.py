"""stream(ADR-0014 板块集成):aihot 前四板块中三个新板块的数据产物。

精选(featured)/全部动态(all)/热点榜(hot)= 每日 run 同 manifest 同
评分的衍生产物,零额外 LLM 成本。产物 markdown 与 digest 同构
(site/src/lib/digest-card.mjs 同一解析器消费),文件落
site/src/content/stream/<kind>-<date>.md,随日报同一 commit 发布。

热点榜=纯规则聚簇:标题 token(英文词+中文 bigram)Jaccard 贪心合并,
热度以独立来源数为主(AIHOT「按事件算、独立来源只算一次」的轻量版);
≥2 独立来源的事件上榜。板块页按日分组,每日随日报更新一次(静态站
节奏,ADR-0014)。
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .assemble import escape_markdown_text
from .config import load_config
from .db import connect_db

logger = logging.getLogger(__name__)

_SIM_THRESHOLD = 0.35          # 标题 token Jaccard 同事件阈值
_STOPWORDS = {
    "the", "a", "an", "of", "in", "to", "for", "on", "with", "and",
    "or", "new", "is", "are", "as", "at", "by", "its", "this", "that",
    "from", "how", "what", "why",
}
_WORD_RE = re.compile(r"[a-z0-9]+")
_CJK_RE = re.compile(r"[一-鿿]+")


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    out = {w for w in _WORD_RE.findall(text)
           if w not in _STOPWORDS and len(w) > 1}
    for run in _CJK_RE.findall(text):
        out.update(run[i:i + 2] for i in range(len(run) - 1))
    return out


def _event_text(m: dict) -> str:
    return m.get("title_zh") or m.get("title") or ""


def cluster_events(members: list[dict],
                   *, threshold: float = _SIM_THRESHOLD) -> list[dict]:
    """贪心聚簇:代表分最高者作种子吸收相似条目;按热度降序返回。

    事件 = {representative, members, sources, source_names, hot};
    热度 = min(独立来源数,5)*12 + 代表展示分//2(来源数为主语义)。
    """
    scored = sorted(members,
                    key=lambda m: (-m.get("display_score", 0),
                                   m["identity_key"]))
    token_sets = [_tokens(_event_text(m)) for m in scored]
    unassigned = list(range(len(scored)))
    events: list[dict] = []
    while unassigned:
        seed = unassigned.pop(0)
        group = [seed]
        rest = []
        for i in unassigned:
            a, b = token_sets[seed], token_sets[i]
            sim = (len(a & b) / len(a | b)) if a and b else 0.0
            (group if sim >= threshold else rest).append(i)
        unassigned = rest
        members_i = [scored[i] for i in group]
        source_names = []
        for m in members_i:
            if m["source_name"] not in source_names:
                source_names.append(m["source_name"])
        rep = members_i[0]     # 组内代表分最高(scored 序保持)
        events.append({
            "representative": rep, "members": members_i,
            "sources": len(source_names), "source_names": source_names,
            "hot": min(len(source_names), 5) * 12
                   + rep.get("display_score", 0) // 2,
        })
    events.sort(key=lambda e: (-e["hot"], -e["sources"]))
    return events


def _esc(text) -> str:
    return escape_markdown_text(str(text or ""))


def _card(m: dict, summaries: dict) -> list[str]:
    """单条目卡片行(### 标题 + 摘要行 + 来源尾行)。"""
    s = summaries.get(m["identity_key"]) or {}
    title = s.get("title_zh") or m.get("title") or m["url"]
    summary = s.get("summary") or (m.get("content_text") or "")[:120]
    reason = s.get("reason") or ""
    tail = (f"[来源]({m['url']})({m['source_name']}"
            f" · 展示分 {m.get('display_score', 0)})")
    lines = [f"### {_esc(title)}", ""]
    if summary:
        lines += [f"- {_esc(summary)}", ""]
    lines += [f"- {_esc(reason)}{tail}" if reason else f"- {tail}", ""]
    return lines


def _frontmatter(kind: str, issue_date: str, count: int) -> list[str]:
    return ["---", f"kind: '{kind}'", f"date: '{issue_date}'",
            "generated: true", f"count: {count}", "---", ""]


def _quote(kind: str) -> str:
    return {
        "featured": "每日精选流 · 同 manifest 同评分 · 按展示分门槛分组",
        "all": "全部动态流 · 当日已评分条目全量(未过线也收录)",
        "hot": "今日热点 · 同事件跨源聚簇 · 独立来源越多越靠前",
    }[kind]


def build_stream_pages(issue_date: str, sections: dict, *,
                       selected: list[dict], rejected: list[dict],
                       summaries: dict) -> dict[str, str]:
    """构建三份板块页 markdown;summaries=identity_key → 摘要行。"""
    out: dict[str, str] = {}

    # featured:按门槛三组(板块名与 digest 产物同构;空组不输出)
    groups = {"headline": [], "featured": [], "glimpse": []}
    for m in selected:
        d = m.get("display_score", 0)
        if d >= sections["headline"]:
            groups["headline"].append(m)
        elif d >= sections["featured"]:
            groups["featured"].append(m)
        else:
            groups["glimpse"].append(m)
    labels = {
        "headline": f"头条(展示分 ≥ {sections['headline']})",
        "featured": (f"精选({sections['featured']}"
                     f"-{sections['headline'] - 1})"),
        "glimpse": "值得一瞥(压线入选)",
    }
    lines = _frontmatter("featured", issue_date, len(selected))
    lines += [f"> {_quote('featured')}", ""]
    for key in ("headline", "featured", "glimpse"):
        if not groups[key]:
            continue
        lines += [f"## {labels[key]}", ""]
        for m in groups[key]:
            lines += _card(m, summaries)
    out["featured"] = "\n".join(lines).rstrip() + "\n"

    # all:单组全量,展示分降序
    everyone = sorted(selected + rejected,
                      key=lambda m: (-m.get("display_score", 0),
                                     m["identity_key"]))
    lines = _frontmatter("all", issue_date, len(everyone))
    lines += [f"> {_quote('all')}", "", "## 全部动态", ""]
    for m in everyone:
        lines += _card(m, summaries)
    out["all"] = "\n".join(lines).rstrip() + "\n"

    # hot:≥2 独立来源的事件上榜
    events = [e for e in cluster_events(selected + rejected)
              if e["sources"] >= 2]
    lines = _frontmatter("hot", issue_date, len(events))
    lines += [f"> {_quote('hot')}", "", "## 今日热点", ""]
    for e in events:
        rep = e["representative"]
        lines += _card({**rep, "display_score": e["hot"]}, summaries)[:2]
        names = "、".join(e["source_names"])
        lines += [f"- {len(e['members'])} 条同事件报道:{names}", ""]
        tail = (f"独立来源 {e['sources']} · 代表展示分"
                f" {e['representative'].get('display_score', 0)}"
                f"[来源]({rep['url']})({rep['source_name']}"
                f" · 展示分 {e['hot']})")
        lines += [f"- {tail}", ""]
    out["hot"] = "\n".join(lines).rstrip() + "\n"
    return out


def rebuild_from_db(conn: sqlite3.Connection, sections: dict,
                    issue_date: str) -> dict[str, str]:
    """回放一期:issue_freeze manifest + analysis 评分 + summary 摘要
    → 三份板块页(首期回填与重放共用)。"""
    row = conn.execute(
        "SELECT manifest_json FROM issue_freeze WHERE issue_date=?",
        (issue_date,)).fetchone()
    if row is None:
        raise ValueError(f"no freeze: {issue_date} 无冻结 manifest")
    manifest = json.loads(row[0])
    by_key = {m["identity_key"]: m for m in manifest}
    analysis: dict[int, tuple] = {}
    for m in manifest:
        a = conn.execute(
            "SELECT score_1, score_2, selected FROM analysis"
            " WHERE entry_id=? ORDER BY id DESC LIMIT 1",
            (m["entry_id"],)).fetchone()
        if a is not None:
            analysis[m["entry_id"]] = tuple(a)
    selected, rejected = [], []
    for m in manifest:
        a = analysis.get(m["entry_id"])
        if a is None:
            continue          # 未评分(如 force_include 无评分)不进流
        member = {**m, "display_score": (a[0] + a[1]) // 2}
        (selected if a[2] else rejected).append(member)
    summaries: dict[str, dict] = {}
    id_to_key = {m["entry_id"]: m["identity_key"] for m in manifest}
    for title_zh, summary, reason, entry_id in conn.execute(
            "SELECT s.title_zh, s.summary, s.reason, s.entry_id"
            " FROM summary s JOIN (SELECT entry_id, MAX(id) mid"
            " FROM summary GROUP BY entry_id) latest"
            " ON s.entry_id=latest.entry_id AND s.id=latest.mid"):
        if entry_id in id_to_key:
            summaries[id_to_key[entry_id]] = {
                "title_zh": title_zh, "summary": summary, "reason": reason}
    return build_stream_pages(issue_date, sections, selected=selected,
                              rejected=rejected, summaries=summaries)


def main(argv: list[str] | None = None) -> int:
    """回填 CLI:--root/--date/--emit-dir → 三份板块 md 落盘。"""
    parser = argparse.ArgumentParser(
        prog="nanmu-engine-stream",
        description="ADR-0014 板块页数据回填(精选/全部动态/热点榜)")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--date", required=True)
    parser.add_argument("--emit-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    config = load_config(args.root)
    conn = connect_db(str(args.root / "engine.db"))
    try:
        pages = rebuild_from_db(conn, config.selection.sections,
                                args.date)
    finally:
        conn.close()
    args.emit_dir.mkdir(parents=True, exist_ok=True)
    for kind, markdown in pages.items():
        (args.emit_dir / f"{kind}-{args.date}.md").write_text(
            markdown, encoding="utf-8")
    logger.info("stage=stream event=emitted date=%s kinds=%s",
                args.date, sorted(pages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
