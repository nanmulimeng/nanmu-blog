"""组装与安全输出(content-editing §3 规则 10;pipeline.md 产物模板)。

纯函数组装(零网络零费用——重组装/续跑复用摘要即零新增付费)+ 落盘
协议(markdown 先落盘,再单事务写 digest_issue draft 行含 content_sha256;
崩溃在中间=无行重组装,幂等)。

安全输出双上下文:模型文本字段(title_zh/summary/reason)按 Markdown
文本上下文转义(控制字符 strip + CommonMark 行内语法字符集反斜杠转义
——模型链接/HTML 语法全部字面呈现);来源 URL 按链接目标上下文构造
(scheme 白名单 http/https,空白/括号/反斜杠百分号编码,URL 永不直接
拼进正文文本)。验收以渲染后 HTML 为准(测试侧起渲染管线)。
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlsplit

from nanmu_engine.config import Config

_MD_PUNCT = set(r"\`*_{}[]()#+-.!<>|~")      # CommonMark 行内语法 ASCII 标点
_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_URL_UNSAFE = {" ": "%20", "(": "%28", ")": "%29", "\\": "%5C"}
# GFM autolink literal 断链(审计 P2-7):反斜杠转义与字符引用都挡不住
# autolink——micromark 在文本内容上匹配,转义/实体先归一为字面字符
# (实测 @astrojs/markdown-remark:`https://evil\.example\.com` 与
# `https&#58;//evil&#46;com` 均仍产 <a>)。在触发前缀的连接点插入零宽
# 字符 U+200B(不可见,渲染与字号不受影响):"www"+ZWSP+"\." 不匹配
# www. 字面前缀;scheme+ZWSP+"://" 同理;本地部分+ZWSP+"@" 断邮箱。
_AUTOLINK_BREAKS = (
    re.compile(r"(?<=[Ww][Ww][Ww])(?=\\.)"),        # www. 前缀
    re.compile(r"(?<=[0-9A-Za-z])(?=://)"),          # scheme:// 前缀
    re.compile(r"(?<=[0-9A-Za-z_+\-])(?=@)"),        # 邮箱 user@ 前缀
)
_ZWSP = "​"


class AssemblyPaused(Exception):
    """组装暂停转人工(强制项安全失败等;期保持当前状态,通知转单元五)。"""


def escape_markdown_text(text: str) -> str:
    """Markdown 文本上下文转义:strip 控制字符(含换行——模型不可构造
    新块)后,行内语法字符集逐字符反斜杠转义(仅转义 `<>&` 挡不住
    `[伪装链接](url)` 语法,实测,故取全标点集);再在 GFM autolink
    触发前缀连接点插入零宽字符断自动链接(见 _AUTOLINK_BREAKS)。"""
    cleaned = _CTRL.sub("", text or "")
    escaped = "".join("\\" + ch if ch in _MD_PUNCT else ch
                      for ch in cleaned)
    for pattern in _AUTOLINK_BREAKS:
        escaped = pattern.sub(_ZWSP, escaped)
    return escaped


def safe_source_url(url: str | None) -> str | None:
    """链接目标上下文:scheme ∈ {http, https} 才入产物(其余→None,
    调用方按 E7 剔除/强制项暂停);破坏链接目标的字符百分号编码。
    URL 本身永不直接拼进正文文本——只经 `[来源](url)` 模板构造。"""
    if not url:
        return None
    try:
        if urlsplit(url).scheme not in ("http", "https"):
            return None
    except ValueError:
        return None
    cleaned = _CTRL.sub("", url)
    return "".join(_URL_UNSAFE.get(ch, ch) for ch in cleaned)


# ---------- 组装(pipeline.md 模板;板块阈值=selection.yaml 运营参数) ----------

@dataclass(frozen=True)
class DigestDraft:
    issue_date: str
    markdown: str
    content_sha256: str
    entry_ids: tuple[int, ...]
    entry_count: int
    model: str
    cost_cny: float
    cost_pending: bool
    safety_excluded: dict[str, str] = field(default_factory=dict)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def assemble_issue(config: Config, issue_date: str, selected: list[dict],
                   summaries: dict[str, dict],
                   cost_snapshot: tuple[float, bool]) -> DigestDraft:
    """纯函数组装:输入=最终产物集合(已过就绪判据)+摘要材料+费用快照
    (issue_cost_snapshot 同一时点同口径)。安全校验:普通项 URL 不合法
    →剔除(safety_excluded);强制项 → AssemblyPaused(转人工)。
    板块内展示分降序(同分 identity_key 升序),强制项固定「值得一瞥」
    末尾;空板块不输出标题(不生成空标题凑结构)。"""
    sections = config.selection.sections           # {headline, featured, glimpse}
    safety_excluded: dict[str, str] = {}

    ready: list[dict] = []
    for m in selected:
        url = safe_source_url(m.get("url"))
        if url is None:
            if m.get("force_included"):
                raise AssemblyPaused(
                    f"safety:强制项 URL 不合法(scheme 非白名单):"
                    f"{m['identity_key']}")
            safety_excluded[m["identity_key"]] = "safety_failed"
            continue
        ready.append({**m, "safe_url": url})

    headline_min = sections["headline"]
    featured_min = sections["featured"]

    def section_of(m: dict) -> str:
        if m["display_score"] >= headline_min:
            return "headline"
        if m["display_score"] >= featured_min:
            return "featured"
        return "glimpse"

    groups: dict[str, list[dict]] = {"headline": [], "featured": [],
                                     "glimpse": []}
    for m in ready:
        groups[section_of(m)].append(m)

    cost_cny, cost_pending = cost_snapshot
    model = config.budget.default_model          # 实际调用模型(非示例 ID)
    lines = [
        "---",
        f"date: '{issue_date}'",
        "generated: true",
        f"ai_model: {model}",
        f"entry_count: {len(ready)}",
        f"cost_cny: {cost_cny:.2f}",
        f"cost_pending: {'true' if cost_pending else 'false'}",
        "---",
        "",
        f"> AI 生成与精选 · 模型 {model} · 成本 ¥{cost_cny:.2f}"
        + ("(含未决预占,为保守上界)" if cost_pending else ""),
        "",
    ]

    def sort_key(m: dict):
        return (-m["display_score"], m["identity_key"])

    if groups["headline"]:
        lines += [f"## 头条(展示分 ≥ {headline_min})", ""]
        for m in sorted(groups["headline"], key=sort_key):
            s = summaries[m["identity_key"]]
            lines += [
                f"### {escape_markdown_text(s['title_zh'])}",
                "",
                f"- {escape_markdown_text(s['summary'])}",
                f"- {escape_markdown_text(s['reason'])}"
                f"[来源]({m['safe_url']})"
                f"({escape_markdown_text(m.get('source_name', ''))}"
                f" · 展示分 {m['display_score']})",
                "",
            ]
    if groups["featured"]:
        lines += [f"## 精选({featured_min}-{headline_min - 1})", ""]
        for m in sorted(groups["featured"], key=sort_key):
            s = summaries[m["identity_key"]]
            lines += [
                f"### {escape_markdown_text(s['title_zh'])}",
                "",
                f"- {escape_markdown_text(s['summary'])}",
                f"- {escape_markdown_text(s['reason'])}"
                f"[来源]({m['safe_url']})"
                f"({escape_markdown_text(m.get('source_name', ''))}"
                f" · 展示分 {m['display_score']})",
                "",
            ]
    if groups["glimpse"]:
        lines += ["## 值得一瞥(压线入选)", ""]
        normal = sorted((m for m in groups["glimpse"]
                         if not m.get("force_included")), key=sort_key)
        forced = sorted((m for m in groups["glimpse"]
                         if m.get("force_included")), key=sort_key)
        for m in normal + forced:                 # 强制项恒末尾
            s = summaries[m["identity_key"]]
            badge = ", 人工纳入" if m.get("force_included") else ""
            lines += [
                f"- [{escape_markdown_text(s['title_zh'])}]({m['safe_url']})"
                f"——{escape_markdown_text(s['summary'])}"
                f"({escape_markdown_text(m.get('source_name', ''))}"
                f" · 展示分 {m['display_score']}{badge})",
                "",
            ]

    markdown = "\n".join(lines).rstrip("\n") + "\n"
    sha = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return DigestDraft(issue_date=issue_date, markdown=markdown,
                       content_sha256=sha,
                       entry_ids=tuple(m["entry_id"] for m in ready),
                       entry_count=len(ready), model=model,
                       cost_cny=cost_cny, cost_pending=cost_pending,
                       safety_excluded=safety_excluded)


# ---------- 落盘协议(单元三写入协议:文件先落盘再单事务) ----------

def write_draft(conn: sqlite3.Connection, draft: DigestDraft,
                path) -> str:
    """markdown 先落盘(文件存在是 draft 行的前提),再单事务
    INSERT/UPDATE digest_issue(status='draft'+markdown_path+content_sha256
    =文件字节 sha256)。重装(draft 期边界变更/异常 D 恢复)UPDATE 同行,
    不重复建行;崩溃在文件落盘后事务前=无行,重组装幂等。"""
    data = draft.markdown.encode("utf-8")
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    now = _utc_now()
    entry_ids = json.dumps(list(draft.entry_ids))
    with conn:
        conn.execute(
            "INSERT INTO digest_issue (issue_date, entry_ids, markdown_path,"
            " content_sha256, cost_cny, status, created_utc, updated_utc)"
            " VALUES (?,?,?,?,?, 'draft', ?, ?)"
            " ON CONFLICT(issue_date) DO UPDATE SET"
            " entry_ids=excluded.entry_ids, markdown_path=excluded.markdown_path,"
            " content_sha256=excluded.content_sha256, cost_cny=excluded.cost_cny,"
            " status='draft', updated_utc=excluded.updated_utc",
            (draft.issue_date, entry_ids, str(path), sha, draft.cost_cny,
             now, now))
    return sha
