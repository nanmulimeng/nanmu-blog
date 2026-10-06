"""发布链:专用工作副本、四中断窗口恢复、线上证据链三步、ops_json 协议
(publish-withdraw §3 规则 1-5)。

状态推进每步证据+同事务落库:commit 成功即回填 git_commit(仍 draft)→
push 后远端接收判定(fetch 后 merge-base --is-ancestor,ls-remote 只示
尖端不能证明历史 SHA 被接收)→ submitted;线上证据链三步(部署 SHA 树内
身份 → 排除后续删除 → URL 可读)→ published 与终态清算同一事务。

恢复一律先查远端与线上、后补记状态,不凭退出码重新生成;查找失败=
证据不足转人工(不把未知当重新生成许可);比对基准=库内持久化身份,
不是工作副本现状(副本可被人为改动)。
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from nanmu_engine.select import _settle_published_sql


class ManualIntervention(Exception):
    """转人工(E8/隔离失败/证据不足):引擎不动现场,人工核实后按命令
    推进(重组装/重试 push 均需显式确认)。"""


@dataclass(frozen=True)
class PublishResult:
    status: str                  # draft / submitted / published
    detail: str | None = None


@dataclass
class PublishContext:
    workdir: Path                                    # 专用工作副本
    remote_url: str
    branch: str = "main"
    digest_dir: str = "site/src/content/digest"
    site_base: str = ""
    fetch_release_sha: Callable[[], str | None] = field(default=lambda: None)
    fetch_url_ok: Callable[[str], bool] = field(default=lambda url: False)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- git 基元(全部经专用副本;禁止 force push / rewrite 历史) ----------

def _git(ctx: PublishContext, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=str(ctx.workdir),
                       capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {args}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def _git_bytes(ctx: PublishContext, *args: str) -> bytes | None:
    r = subprocess.run(["git", *args], cwd=str(ctx.workdir),
                       capture_output=True)
    return r.stdout if r.returncode == 0 else None


def _rel_path(ctx: PublishContext, markdown_path: str) -> str:
    p = Path(markdown_path)
    if not p.is_absolute():
        p = ctx.workdir / p
    return p.resolve().relative_to(Path(ctx.workdir).resolve()).as_posix()


def _blob_sha(ctx: PublishContext, rev: str, rel: str) -> str | None:
    data = _git_bytes(ctx, "show", f"{rev}:{rel}")
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _is_ancestor(ctx: PublishContext, sha: str, ref: str) -> bool:
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", sha, ref],
        cwd=str(ctx.workdir), capture_output=True)
    return r.returncode == 0


def _digest_rel(ctx: PublishContext, issue_date: str) -> str:
    return f"{ctx.digest_dir}/{issue_date}.md"


# ---------- verify(质量门禁最小实现:push 前拦坏 markdown) ----------

_FM_KEYS = ("date", "generated", "ai_model", "entry_count", "cost_cny",
            "cost_pending")


def verify_draft(path: Path) -> None:
    """M1 最小门禁:文件存在且 frontmatter 六字段齐(完整质量门禁引用
    development/quality-gates.md,缓存验证属 site 构建链)。失败→不 push。"""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.+?)\n---\n", text, re.S)
    if not m:
        raise ValueError(f"verify:frontmatter 缺失({path})")
    for key in _FM_KEYS:
        if not re.search(rf"^{key}: ", m.group(1), re.M):
            raise ValueError(f"verify:frontmatter 缺字段 {key}({path})")


# ---------- 副本同步与跨期隔离(规则 4:push 前强制) ----------

def _sync_workdir(ctx: PublishContext, issue_date: str) -> None:
    """fetch 后:本地有未推送提交时逐提交核对变更集只含本期文件(他期
    未推送提交会被本次 push 带出→不 push 转人工);无未推送→fast-forward
    同步;分叉(远端前进且与本地分叉)→E8 转人工。"""
    _git(ctx, "fetch", "origin")
    rel = _digest_rel(ctx, issue_date)
    ahead = [s for s in _git(
        ctx, "rev-list", f"origin/{ctx.branch}..HEAD").split() if s]
    for sha in ahead:
        files = [f for f in _git(
            ctx, "diff-tree", "--no-commit-id", "--name-only", "-r",
            sha).splitlines() if f]
        foreign = [f for f in files if f != rel]
        if foreign:
            raise ManualIntervention(
                f"isolation:副本存在他期未推送提交,本次 push 会带出 "
                f"({sha[:12]}:{foreign})——不 push,转人工")
    head = _git(ctx, "rev-parse", "HEAD")
    origin = _git(ctx, "rev-parse", f"origin/{ctx.branch}")
    base = _git(ctx, "merge-base", "HEAD", f"origin/{ctx.branch}")
    if head == origin:
        return                                  # 已同步
    if base == origin:                          # 本地落后 → ff 同步
        _git(ctx, "merge", "--ff-only", f"origin/{ctx.branch}")
    elif base != head:                          # 双向分叉 → E8
        raise ManualIntervention(
            "push-conflict:远端已前进且与本地分叉(E8)——转人工")


def _commit_digest(ctx: PublishContext, issue_date: str, rel: str,
                   expected_sha: str) -> str:
    """幂等提交:HEAD 树内该路径身份已=库内身份→复用 HEAD(不造空提交);
    否则 verify→add→commit;返回提交 SHA(commit 成功即回填,仍 draft)。"""
    head = _git(ctx, "rev-parse", "HEAD")
    if _blob_sha(ctx, head, rel) == expected_sha:
        return head
    verify_draft(ctx.workdir / rel)
    _git(ctx, "add", rel)
    _git(ctx, "commit", "-q", "-m", f"digest: {issue_date}")
    return _git(ctx, "rev-parse", "HEAD")


# ---------- 线上证据链三步(规则 2:published 的证据是线上事实) ----------

def _online_evidence(ctx: PublishContext, issue_date: str,
                     expected_sha: str) -> bool:
    """①线上部署 SHA 提交树中目标路径存在且树内文件字节 sha256=预期
    身份(经 git cat-file;构建合并多提交不要求线上 SHA=日报 commit,但
    树内内容身份必须相等);②排除后续删除/修改(origin/main 尖端树内
    仍为该身份);③对应日报 URL HTTP 可读(渲染一致性走 site 校验)。"""
    deployed = ctx.fetch_release_sha()
    if not deployed:
        return False
    rel = _digest_rel(ctx, issue_date)
    if _blob_sha(ctx, deployed, rel) != expected_sha:
        return False
    tip = _git(ctx, "rev-parse", f"origin/{ctx.branch}")
    if _blob_sha(ctx, tip, rel) != expected_sha:
        return False
    url = f"{ctx.site_base}/digest/{issue_date}/"
    return bool(ctx.fetch_url_ok(url))


def _mark_published(conn, issue_date: str, final_keys: list[str]) -> None:
    """published 状态推进与终态清算(进产物 used/未进 rejected+均清
    claim)同一事务(publish-withdraw 规则 2 表)。"""
    with conn:
        conn.execute(
            "UPDATE digest_issue SET status='published', updated_utc=?"
            " WHERE issue_date=?", (_now(), issue_date))
        _settle_published_sql(conn, issue_date, final_keys)


# ---------- 发布主流程 ----------

def publish_issue(conn, issue_date: str, ctx: PublishContext, *,
                  final_keys: list[str]) -> PublishResult:
    """draft→published 推进:同步与隔离检查→commit(回填 SHA,仍 draft)
    →push(远端接收=分支可达性)→submitted→线上证据链三步→published
    同事务清算。线上证据不可得→保持 submitted(E9 只重查)。"""
    row = conn.execute(
        "SELECT markdown_path, content_sha256, status FROM digest_issue"
        " WHERE issue_date=?", (issue_date,)).fetchone()
    if row is None:
        raise ManualIntervention(f"no-draft:{issue_date} 无 draft 行(先组装)")
    markdown_path, expected, status = row
    if status not in ("draft", "submitted"):
        return PublishResult(status, "终态/失败期不自动发布")
    rel = _rel_path(ctx, markdown_path)
    if status == "submitted":
        # E9:只重查线上,不重做评分/摘要/重组
        if _online_evidence(ctx, issue_date, expected):
            _mark_published(conn, issue_date, final_keys)
            return PublishResult("published", "submitted 存量线上确认")
        return PublishResult("submitted", "E9:等待线上证据")

    _sync_workdir(ctx, issue_date)
    commit = _commit_digest(ctx, issue_date, rel, expected)
    with conn:
        conn.execute(
            "UPDATE digest_issue SET git_commit=?, updated_utc=?"
            " WHERE issue_date=?", (commit, _now(), issue_date))
    _git(ctx, "push", "origin", ctx.branch)
    _git(ctx, "fetch", "origin")
    if not _is_ancestor(ctx, commit, f"origin/{ctx.branch}"):
        return PublishResult("draft", "push 未确认被远端接收")
    with conn:
        conn.execute(
            "UPDATE digest_issue SET status='submitted', updated_utc=?"
            " WHERE issue_date=?", (_now(), issue_date))
    if _online_evidence(ctx, issue_date, expected):
        _mark_published(conn, issue_date, final_keys)
        return PublishResult("published")
    return PublishResult("submitted", "E9:等待线上证据")


# ---------- 四中断窗口恢复(规则 3:先查证据后补记,单窗口单步) ----------

def recover_issue(conn, issue_date: str,
                  ctx: PublishContext) -> PublishResult:
    """按 digest_issue 行现状分派:无行→W1(副本按路径找提交,复用提交
    补记 draft);有行无 git_commit→W2(以库内 content_sha256 为预期在
    git 历史找提交补填;查找失败=证据不足转人工);draft 有 git_commit
    →W3(分支可达性判定;非 origin/main 祖先不判 submitted);submitted
    →W4(线上证据链三步→published+清算,幂等)。全程零 LLM 调用。"""
    _git(ctx, "fetch", "origin")
    rel = _digest_rel(ctx, issue_date)
    row = conn.execute(
        "SELECT markdown_path, content_sha256, status, git_commit, entry_ids"
        " FROM digest_issue WHERE issue_date=?", (issue_date,)).fetchone()

    if row is None:                                     # W1
        commits = [c for c in _git(
            ctx, "log", "--format=%H", "--", rel).split() if c]
        if not commits:
            raise ManualIntervention(
                f"证据不足:{issue_date} 无 draft 行且副本无该期产物提交"
                "——转人工(人工确认未提交后可重组装,评分/摘要全复用)")
        commit = commits[0]                             # 该路径最新提交
        blob_sha = _blob_sha(ctx, commit, rel)
        with conn:
            conn.execute(
                "INSERT INTO digest_issue (issue_date, entry_ids,"
                " markdown_path, content_sha256, git_commit, status,"
                " created_utc, updated_utc)"
                " VALUES (?, '[]', ?, ?, ?, 'draft', ?, ?)",
                (issue_date, str(ctx.workdir / rel), blob_sha, commit,
                 _now(), _now()))
        return PublishResult("draft", f"W1 补记(git_commit={commit[:12]})")

    markdown_path, expected, status, git_commit, entry_ids_json = row
    if git_commit is None:                              # W2
        for c in [x for x in _git(
                ctx, "log", "--format=%H", "--", rel).split() if x]:
            if _blob_sha(ctx, c, rel) == expected:
                with conn:
                    conn.execute(
                        "UPDATE digest_issue SET git_commit=?, updated_utc=?"
                        " WHERE issue_date=?", (c, _now(), issue_date))
                return PublishResult(
                    "draft", f"W2 补填 git_commit={c[:12]}(以库内身份匹配,"
                    "不受副本现状影响)")
        raise ManualIntervention(
            f"证据不足:库内身份 {expected} 在本地与远端历史均无内容"
            "匹配的提交——转人工(不把未知当重新生成许可)")

    if status == "draft":                               # W3
        if _is_ancestor(ctx, git_commit, f"origin/{ctx.branch}"):
            with conn:
                conn.execute(
                    "UPDATE digest_issue SET status='submitted',"
                    " updated_utc=? WHERE issue_date=?",
                    (_now(), issue_date))
            return PublishResult("submitted", "W3 补记")
        return PublishResult(
            "draft", "W3:git_commit 非 origin/main 祖先,不判 submitted")

    if status == "submitted":                           # W4
        if _online_evidence(ctx, issue_date, expected):
            ids = json.loads(entry_ids_json or "[]")
            final_keys = [k for (k,) in conn.execute(
                f"SELECT identity_key FROM entry WHERE id IN "
                f"({','.join('?' * len(ids))})", ids)] if ids else []
            _mark_published(conn, issue_date, final_keys)
            return PublishResult("published", "W4 线上确认+终态清算")
        return PublishResult("submitted", "W4:线上证据未就绪/路径 404")
    return PublishResult(status, "无需恢复")


# ---------- ops_json 内容操作记录协议(规则 5;撤回/重上/纠错消费) ----------

_ONLINE_OPS = {"relist", "relist_corrected", "correct"}
_VISIBLE = {"withdraw": "withdrawn", "relist": "relisted",
            "relist_corrected": "relisted", "correct": "published"}


def _load_ops(conn, issue_date: str) -> list[dict]:
    row = conn.execute(
        "SELECT ops_json FROM digest_issue WHERE issue_date=?",
        (issue_date,)).fetchone()
    if row is None:
        raise KeyError(f"digest_issue 行不存在:{issue_date}")
    return json.loads(row[0]) if row[0] else []


def _save_ops(conn, issue_date: str, ops: list[dict]) -> None:
    conn.execute(
        "UPDATE digest_issue SET ops_json=?, updated_utc=? WHERE issue_date=?",
        (json.dumps(ops, ensure_ascii=False), _now(), issue_date))


def append_op(conn, issue_date: str, op: str, target_sha256: str) -> int:
    """操作开始即 append 未完成项(写/删文件之前)——待执行目标版本的
    持久化,不依赖现算副本。撤回 target=固定值 ABSENT。返回 seq。"""
    with conn:
        ops = _load_ops(conn, issue_date)
        seq = len(ops) + 1
        ops.append({"seq": seq, "op": op, "target_sha256": target_sha256,
                    "stages": {}})
        _save_ops(conn, issue_date, ops)
    return seq


def update_op_stage(conn, issue_date: str, seq: int, stage: str,
                    value: str) -> None:
    """阶段补记(commit 成功/push 成功)。"""
    with conn:
        ops = _load_ops(conn, issue_date)
        item = next(o for o in ops if o["seq"] == seq)
        item["stages"][stage] = value
        _save_ops(conn, issue_date, ops)


def confirm_op(conn, issue_date: str, seq: int, *,
               confirmed_utc: str) -> None:
    """线上确认完成→置 confirmed_utc;在线类操作(relist/relist_corrected/
    correct)同一事务 UPDATE content_sha256=该 op 的 target(当前确认
    版本随确认前进;撤回不动)。"""
    with conn:
        ops = _load_ops(conn, issue_date)
        item = next(o for o in ops if o["seq"] == seq)
        item["stages"]["confirmed_utc"] = confirmed_utc
        _save_ops(conn, issue_date, ops)
        if item["op"] in _ONLINE_OPS:
            conn.execute(
                "UPDATE digest_issue SET content_sha256=? WHERE issue_date=?",
                (item["target_sha256"], issue_date))


def visible_status(conn, issue_date: str) -> str:
    """当前可见状态=最新 confirmed 项的 op 类型;无 confirmed 内容操作
    →按 digest_issue.status(重启后仅凭 DB 可复现判定)。"""
    confirmed = [o for o in _load_ops(conn, issue_date)
                 if o["stages"].get("confirmed_utc")]
    if confirmed:
        return _VISIBLE[confirmed[-1]["op"]]
    return conn.execute(
        "SELECT status FROM digest_issue WHERE issue_date=?",
        (issue_date,)).fetchone()[0]
