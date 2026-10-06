"""零成本预筛(纯函数;data-ingestion §3 规则 7-9、§4 输出③)。

两层排除(顺序固定,全部本地零成本):内容/编辑排除适用全体成员
(含本期已选中——运营参数与 override 续跑时可变);占用排除只排他期。
复用分层复用 ledger.apply_n_new(recoverable=至少一条当前请求身份有效
响应,单义;截断排序同一规则)。四去向全覆盖不变量由结构保证:
to_score ∪ recoverable ∪ excluded ∪ capped = manifest 全体,恰一去向。
"""

from __future__ import annotations

from dataclasses import dataclass

from nanmu_engine.config import Config
from nanmu_engine.ledger import apply_n_new

REASON_TITLE_BLACKLIST = "title_blacklist"
REASON_SOURCE_EXCLUDED = "source_excluded"
REASON_EMPTY_CONTENT = "empty_content"
REASON_USED = "used"
REASON_OVERRIDE_EXCLUDE = "override_exclude"
REASON_OCCUPIED_OTHER = "occupied_other_issue"


@dataclass(frozen=True)
class PrescreenResult:
    to_score: tuple      # 有序,前 N_new 条确需新增付费评分的合格成员
    recoverable: tuple   # 成员+needs/analysis_ref(进度保留,不占 N 不截断)
    excluded: tuple      # ((identity_key, reason), ...)
    capped: tuple        # ((identity_key, rank), ...) 排序在 N_new 之外


def _content_exclusion(member: dict, config: Config,
                       override_exclude: set) -> str | None:
    """内容/编辑排除(规则 1-5,顺序固定;适用全体成员)。"""
    title = member.get("title") or ""
    if any(word and word in title for word in config.selection.title_blacklist):
        return REASON_TITLE_BLACKLIST
    source_name = member.get("source_name")
    if any(entry.name == source_name for entry in config.sources.exclude):
        return REASON_SOURCE_EXCLUDED
    content = member.get("content_text")
    if content is None or not content.strip():
        return REASON_EMPTY_CONTENT
    if member["identity_key"] in override_exclude:
        return REASON_OVERRIDE_EXCLUDE
    return None


def prescreen(manifest: list, config: Config, issue_date: str,
              occupancy: dict, override_exclude: set, reuse_snapshot: dict,
              n_new: int) -> PrescreenResult:
    """预筛(纯函数,零网络零付费零副作用;不查 receipt,不解读
    force_include——强制项与普通成员同规则,被 cap/排除时由四去向
    结构保证可见,组装边界消费)。occupancy={identity_key:
    (entry.status, claim_issue)};override_exclude=override 表 exclude
    命中键集;reuse_snapshot=单元二 reusable_scores 只读判定结果。
    """
    excluded: list = []
    survivors: list = []
    for member in manifest:
        key = member["identity_key"]
        status, claim_issue = occupancy.get(key, ("pending", None))
        reason = _content_exclusion(member, config, override_exclude)
        if reason is None and status == "used":    # 规则 4(内容层序内)
            reason = REASON_USED
        if reason is None and status == "selected" and claim_issue \
                and claim_issue != issue_date:
            reason = REASON_OCCUPIED_OTHER         # 规则 6:只排他期
        if reason is None:
            survivors.append(member)
        else:
            excluded.append((key, reason))

    layered = apply_n_new(survivors, reuse_snapshot, n_new=n_new)
    recoverable = []
    for member in layered["recoverable"]:
        snap = reuse_snapshot.get(member["identity_key"], {})
        recoverable.append({**member,
                            "needs": snap.get("needs", []),
                            "analysis_ref": snap.get("analysis_ref")})
    capped = [(m["identity_key"], rank) for rank, m in
              enumerate(layered["capped"], start=1)]
    return PrescreenResult(
        to_score=tuple(layered["to_score"]),
        recoverable=tuple(recoverable),
        excluded=tuple(excluded),
        capped=tuple(capped))
