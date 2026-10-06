"""prescreen 零成本预筛测试(种子=data-ingestion 验收 8/9a-d/10/11;
纯函数:同 manifest+同快照+同 N_new → 同结果,零付费零副作用)。"""

import dataclasses
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nanmu_engine.collect import collect_once
from nanmu_engine.config import (ExcludeEntry, SourceEntry, SourcesConfig,
                                 load_config)
from nanmu_engine.db import connect_db, migrate
from nanmu_engine.prescreen import prescreen

from test_collect import _add_item, _add_source, _make_upstream

ENGINE_ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 6, 8, 30, tzinfo=timezone.utc)
ISSUE = "2026-10-06"


@pytest.fixture
def env(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    config = load_config(ENGINE_ROOT)
    return conn, config, tmp_path


def _cfg(config, blacklist=(), dead=()):
    return dataclasses.replace(
        config,
        selection=dataclasses.replace(config.selection,
                                      title_blacklist=tuple(blacklist)),
        sources=SourcesConfig(1, "T2", config.sources.sources, tuple(dead)))


def _m(i, *, tier="T1", title=None, content="body", force=False):
    return {"identity_key": f"url:https://e.com/{i}", "entry_id": i,
            "url": f"https://e.com/{i}", "title": title or f"t{i}",
            "source_name": "src-a", "source_tier": tier,
            "published_utc": None,
            "discovered_utc": f"2026-10-06T00:{i:02d}:00Z",
            "content_text": content, "content_hash": f"h{i}",
            "force_include": force}


def _snap(members, **per_key):
    base = {m["identity_key"]: {"score_1": None, "score_2": None,
                                "needs": ["score-1", "score-2"],
                                "analysis_ref": None} for m in members}
    base.update(per_key)
    return base


def _occupancy(members, **per_key):
    base = {m["identity_key"]: ("pending", None) for m in members}
    base.update(per_key)
    return base


def _union(result):
    covered = [m["identity_key"] for m in result.to_score]
    covered += [m["identity_key"] for m in result.recoverable]
    covered += [ik for ik, _ in result.excluded]
    covered += [ik for ik, _ in result.capped]
    return covered


# ---------- 验收 8:预筛矩阵与占用分层 ----------

def test_prescreen_matrix_and_occupancy(env):
    conn, config, tmp_path = env
    cfg = _cfg(config, blacklist=["广告"], dead=[ExcludeEntry("src-dead", "坏源")])
    members = [
        _m(1, title="广告:点这"),                       # 1 黑名单
        dict(_m(2), source_name="src-dead"),            # 2 死源
        _m(3, content="   \n  "),                       # 3 空白正文
        _m(4),                                          # 4 used
        _m(5),                                          # 5 override
        _m(6),                                          # 6 本期 selected → recoverable
        _m(7),                                          # 7 他期 selected → 占用排除
        _m(8),                                          # 8 普通 → to_score
        _m(9),                                          # 9 本期 selected 命中 override → excluded
    ]
    occupancy = _occupancy(
        members,
        **{_m(4)["identity_key"]: ("used", None),
           _m(6)["identity_key"]: ("selected", ISSUE),
           _m(7)["identity_key"]: ("selected", "2026-10-05"),
           _m(9)["identity_key"]: ("selected", ISSUE)})
    override = {_m(5)["identity_key"], _m(9)["identity_key"]}
    snap = _snap(members, **{_m(6)["identity_key"]: {
        "score_1": True, "score_2": True, "needs": [], "analysis_ref": 42}})
    result = prescreen(members, cfg, ISSUE, occupancy, override, snap, 10)
    excluded = dict(result.excluded)
    assert excluded[_m(1)["identity_key"]] == "title_blacklist"
    assert excluded[_m(2)["identity_key"]] == "source_excluded"
    assert excluded[_m(3)["identity_key"]] == "empty_content"
    assert excluded[_m(4)["identity_key"]] == "used"
    assert excluded[_m(5)["identity_key"]] == "override_exclude"
    assert excluded[_m(7)["identity_key"]] == "occupied_other_issue"
    # 本期 selected 新命中 override → 移入 excluded 带原因(内容层适用全体)
    assert excluded[_m(9)["identity_key"]] == "override_exclude"
    # 本期 selected 续跑保留 recoverable;普通成员进 to_score
    rec = {m["identity_key"]: m for m in result.recoverable}
    assert _m(6)["identity_key"] in rec
    assert [m["identity_key"] for m in result.to_score] == [_m(8)["identity_key"]]
    # 全覆盖不变量:四去向并集=全体成员,恰一去向
    assert sorted(_union(result)) == sorted(m["identity_key"] for m in members)
    assert len(_union(result)) == len(members)


def test_prescreen_deterministic_order(env):
    conn, config, tmp_path = env
    members = ([_m(i, tier="T1") for i in range(6)]
               + [_m(10 + i, tier="T2") for i in range(4)])
    snap = _snap(members)
    occupancy = _occupancy(members)
    r1 = prescreen(members, config, ISSUE, occupancy, set(), snap, 4)
    shuffled = list(members)
    random.Random(7).shuffle(shuffled)
    r2 = prescreen(shuffled, config, ISSUE, occupancy, set(), snap, 4)
    assert [m["identity_key"] for m in r1.to_score] == \
           [m["identity_key"] for m in r2.to_score]
    assert list(r1.capped) == list(r2.capped)
    # 排序:T1 优先 → discovered_utc 降序(T1 组内 05..00 降序)
    tiers = [m["source_tier"] for m in r1.to_score]
    assert tiers == ["T1"] * 4
    assert r1.to_score[0]["identity_key"] == "url:https://e.com/5"


# ---------- 验收 9:N_new=0 不裁已有成果(a-d 四子场景) ----------

def test_n_zero_all_done_stays_recoverable(env):
    conn, config, tmp_path = env
    m = _m(1)
    snap = _snap([m], **{m["identity_key"]: {
        "score_1": True, "score_2": True, "needs": [], "analysis_ref": 1}})
    occupancy = _occupancy([m], **{m["identity_key"]: ("selected", ISSUE)})
    result = prescreen([m], config, ISSUE, occupancy, set(), snap, 0)
    assert not result.to_score and not result.capped   # 零新增网络调用
    assert len(result.recoverable) == 1
    assert _union(result) == [m["identity_key"]]


def test_n_zero_partial_progress_recoverable_with_needs(env):
    conn, config, tmp_path = env
    m = _m(2)   # 评分响应已持久化一条、尚未 selected
    snap = _snap([m], **{m["identity_key"]: {
        "score_1": True, "score_2": None, "needs": ["score-2"],
        "analysis_ref": None}})
    result = prescreen([m], config, ISSUE, _occupancy([m]), set(), snap, 0)
    # 部分完成 → recoverable(needs 只补缺失,不因截断丢失)
    assert len(result.recoverable) == 1 and not result.to_score
    assert result.recoverable[0]["needs"] == ["score-2"]
    assert _union(result) == [m["identity_key"]]


def test_recoverable_is_not_assembly_proof(env):
    # 接口断言:recoverable 只带进度字段,无 ready/assembled 类标志
    conn, config, tmp_path = env
    m = _m(3)
    snap = _snap([m], **{m["identity_key"]: {
        "score_1": True, "score_2": True, "needs": [], "analysis_ref": None}})
    result = prescreen([m], config, ISSUE, _occupancy([m]), set(), snap, 0)
    assert set(result.recoverable[0]) >= {"needs", "analysis_ref"}
    assert not any(k in result.recoverable[0]
                   for k in ("ready", "assembled", "publishable"))
    assert not hasattr(result, "ready")


def test_n_zero_identity_changed_goes_to_capped(env):
    # d:当前请求身份已变化 → 复用判定不命中 → 参与排序,N_new=0 落 capped 可见
    conn, config, tmp_path = env
    m = _m(4)
    occupancy = _occupancy([m], **{m["identity_key"]: ("selected", ISSUE)})
    result = prescreen([m], config, ISSUE, occupancy, set(), _snap([m]), 0)
    assert not result.recoverable and not result.to_score
    assert result.capped == ((m["identity_key"], 1),)     # 带序号可见
    assert _union(result) == [m["identity_key"]]


# ---------- 验收 10:强制项截断可见性 ----------

def test_force_member_visible_when_capped_or_excluded(env):
    conn, config, tmp_path = env
    cfg = _cfg(config, blacklist=["广告"])
    capped_force = _m(1, force=True)
    excluded_force = _m(2, title="广告:强推", force=True)
    members = [capped_force, excluded_force]
    result = prescreen(members, cfg, ISSUE, _occupancy(members), set(),
                       _snap(members), 0)
    capped_keys = {ik for ik, _ in result.capped}
    excluded_keys = {ik for ik, _ in result.excluded}
    # 消费方可据此识别"强制项未完成评分"→ 暂停,不静默发布
    assert capped_force["identity_key"] in capped_keys
    assert excluded_force["identity_key"] in excluded_keys
    assert sorted(_union(result)) == sorted(m["identity_key"] for m in members)


# ---------- 验收 11:平局收敛(item.id 小者胜;行序无关) ----------

def test_tie_convergence_item_id_wins(env):
    conn, config, tmp_path = env
    up, path = _make_upstream(tmp_path)
    sid = _add_source(up, "src-a")
    _add_item(up, sid, "https://e.com/x", "t-first",
              fetched=T0 - timedelta(hours=1), content="id-1-content")
    _add_item(up, sid, "https://e.com/x/", "t-second",
              fetched=T0 - timedelta(minutes=30), content="id-2-content")
    cfg = dataclasses.replace(
        config, sources=SourcesConfig(
            1, "T2", (SourceEntry("src-a", "T1", 100),), ()))
    r = collect_once(conn, path, cfg, ISSUE, T0)
    # 同源同 tier 同 name → item.id 小者胜(最终平局键;正文不保证唯一)
    assert r.manifest[0]["content_text"] == "id-1-content"

    # 行序颠倒(独立库:先插原第二行 → 它拿更小 item.id 胜出)
    other = tmp_path / "b"
    other.mkdir()
    up2, path2 = _make_upstream(other)
    sid2 = _add_source(up2, "src-a")
    _add_item(up2, sid2, "https://e.com/x", "t-second",
              fetched=T0 - timedelta(hours=1), content="second-first-insert")
    _add_item(up2, sid2, "https://e.com/x/", "t-first",
              fetched=T0 - timedelta(minutes=30), content="first-late-insert")
    c2 = connect_db(str(other / "engine.db"))
    migrate(c2)
    r2 = collect_once(c2, path2, cfg, ISSUE, T0)
    assert r2.manifest[0]["content_text"] == "second-first-insert"
