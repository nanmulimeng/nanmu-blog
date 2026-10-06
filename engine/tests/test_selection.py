"""入选判断与 claim 占用协议测试(种子=content-editing 验收 1/4/6/9;
§3 规则 4/6/7/9;纯函数判定 + 持久化协议,零 LLM)。"""

import itertools
from pathlib import Path

import pytest

from nanmu_engine.config import load_config
from nanmu_engine.db import connect_db, migrate

ENGINE_ROOT = Path(__file__).resolve().parents[1]

from nanmu_engine.select import (
    FinalSetResult,
    apply_selection,
    check_claim_invariant,
    compute_final_set,
    decide_selection,
    release_abandoned_issue,
    settle_published,
)

_ids = itertools.count(300)


@pytest.fixture
def env(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    load_config(ENGINE_ROOT)
    return conn


def _seed_entry(conn, *, tier="T1", status="scored", claim=None, identity=None):
    key = identity or f"url:https://example.com/{next(_ids)}"
    cur = conn.execute(
        "INSERT INTO entry (identity_key, url, title, source_name, source_tier,"
        " discovered_utc, content_text, status, claim_issue)"
        " VALUES (?, ?, 't', 'src', ?, '2026-10-06T00:00:00Z', 'b', ?, ?)",
        (key, f"https://example.com/{next(_ids)}", tier, status, claim))
    conn.commit()
    return {"entry_id": cur.lastrowid, "identity_key": key,
            "source_tier": tier}


def _analysis_row(conn, member, s1, s2, selected=0):
    conn.execute(
        "INSERT INTO analysis (entry_id, prompt_version, model, score_1,"
        " score_2, selected, receipt_ids, created_utc)"
        " VALUES (?, 'pv', 'deepseek-flash', ?, ?, ?, '[]',"
        " '2026-10-06T00:00:00Z')",
        (member["entry_id"], s1, s2, selected))
    conn.commit()
    return {**member, "score_1": s1, "score_2": s2}


def _entry_row(conn, identity):
    return conn.execute(
        "SELECT status, claim_issue FROM entry WHERE identity_key=?",
        (identity,)).fetchone()


# ---------- 验收 1:评分与入选分离(同分数随当期门槛/override 变) ----------

def test_decide_selection_tier_thresholds_and_force_include(env):
    conn = env
    t1 = _analysis_row(conn, _seed_entry(conn, tier="T1"), 70, 70)
    t2 = _analysis_row(conn, _seed_entry(conn, tier="T2"), 75, 74)  # 均分 74<75
    t2_pass = _analysis_row(conn, _seed_entry(conn, tier="T2"), 76, 74)  # 75
    low = _analysis_row(conn, _seed_entry(conn, tier="T2"), 20, 20)
    override = {low["identity_key"]: "force_include"}
    result = decide_selection([t1, t2, t2_pass, low],
                              {"T1": 60, "T2": 75}, override)
    by_key = {v.identity_key: v for v in result.selected + result.rejected}
    assert by_key[t1["identity_key"]].selected is True
    assert by_key[t1["identity_key"]].display_score == 70
    assert by_key[t2["identity_key"]].selected is False       # 落选 rejected
    assert by_key[t2_pass["identity_key"]].selected is True
    # force_include 越过门槛但带标注位(不绕过来源/安全/预算)
    assert by_key[low["identity_key"]].selected is True
    assert by_key[low["identity_key"]].force_included is True
    # 同双分 T2 在门槛 75 的期落选、门槛 60 的期入选(分离:分数不变判定变)
    result_t2_low = decide_selection([t2], {"T1": 60, "T2": 60}, {})
    assert result_t2_low.selected[0].identity_key == t2["identity_key"]


# ---------- 验收 4:claim 协议全事件 ----------

def test_apply_selection_writes_claim_and_analysis(env):
    conn = env
    m = _analysis_row(conn, _seed_entry(conn, status="scored"), 80, 82)
    r = _analysis_row(conn, _seed_entry(conn, status="scored"), 30, 30)
    result = decide_selection([m, r], {"T1": 60, "T2": 75}, {})
    apply_selection(conn, "2026-10-06", result)
    assert _entry_row(conn, m["identity_key"]) == ("selected", "2026-10-06")
    assert _entry_row(conn, r["identity_key"]) == ("rejected", None)  # 不写 claim
    assert conn.execute("SELECT selected FROM analysis WHERE entry_id=?",
                        (m["entry_id"],)).fetchone()[0] == 1


def test_settle_published_used_and_rejected_clear_claim(env):
    # published 终态清算:进产物 used+清;未进(override 剔除/裁剪)rejected+清
    conn = env
    a, b, c = (_seed_entry(conn, status="selected", claim="2026-10-06")
               for _ in range(3))
    settle_published(conn, "2026-10-06", [a["identity_key"]])
    assert _entry_row(conn, a["identity_key"]) == ("used", None)
    assert _entry_row(conn, b["identity_key"]) == ("rejected", None)
    assert _entry_row(conn, c["identity_key"]) == ("rejected", None)
    # 无 rejected 持旧 claim 的混合事实
    n = conn.execute("SELECT COUNT(*) FROM entry WHERE status='rejected'"
                     " AND claim_issue IS NOT NULL").fetchone()[0]
    assert n == 0


def test_release_abandoned_issue(env):
    conn = env
    a = _seed_entry(conn, status="selected", claim="2026-10-06")
    b = _seed_entry(conn, status="used", claim=None)          # 他期 used 不动
    release_abandoned_issue(conn, "2026-10-06")
    assert _entry_row(conn, a["identity_key"]) == ("scored", None)
    assert _entry_row(conn, b["identity_key"]) == ("used", None)


def test_check_claim_invariant_catches_dirty_rows(env):
    conn = env
    _seed_entry(conn, status="selected", claim="2026-10-06")  # 正常
    dirty = _seed_entry(conn, status="selected", claim=None)
    bad = check_claim_invariant(conn)
    assert dirty["identity_key"] in bad and len(bad) == 1


# ---------- 验收 6:失败隔离与最终产物集合(规则 6/9) ----------

def _sel_member(identity, *, force=False, score=80, has_summary=True,
                score_done=True):
    return {"identity_key": identity, "entry_id": abs(hash(identity)) % 10**6,
            "source_tier": "T1", "display_score": score,
            "force_included": force, "has_summary": has_summary,
            "score_done": score_done}


def test_final_set_normal_missing_summary_excluded_others_assemble():
    members = [_sel_member("m1"), _sel_member("m2", has_summary=False),
               _sel_member("m3")]
    out = compute_final_set(members, overrides={})
    assert isinstance(out, FinalSetResult)
    assert [m["identity_key"] for m in out.final] == ["m1", "m3"]
    assert out.excluded["m2"] == "summary_failed"
    assert out.paused_reason is None and out.zero_qualified is False


def test_final_set_force_member_incomplete_pauses():
    members = [_sel_member("f1", force=True, has_summary=False),
               _sel_member("m1")]
    out = compute_final_set(members, overrides={"f1": "force_include"})
    assert out.paused_reason == "force_member_incomplete"
    assert out.final == [] and out.zero_qualified is False


def test_final_set_force_over_limit_pauses():
    members = [_sel_member(f"f{i}", force=True) for i in range(16)]
    out = compute_final_set(members,
                            overrides={f"f{i}": "force_include"
                                       for i in range(16)})
    assert out.paused_reason == "force_over_limit"    # F=16 > 15


def test_final_set_force_one_plus_fifteen_normal_keeps_fourteen():
    members = ([_sel_member("f1", force=True)]
               + [_sel_member(f"m{i}", score=90 - i) for i in range(15)])
    out = compute_final_set(members, overrides={"f1": "force_include"})
    assert out.paused_reason is None
    keys = [m["identity_key"] for m in out.final]
    assert keys[0] == "f1" or "f1" in keys             # 1 强制
    assert len(keys) == 15                              # 1+14
    # 被裁者 count_capped,不丢失
    assert len(out.excluded) == 1
    assert "count_capped" in next(iter(out.excluded.values()))


def test_final_set_empty_is_zero_qualified_not_paused():
    out = compute_final_set([], overrides={})
    assert out.zero_qualified is True and out.paused_reason is None


def test_final_set_combined_no_mixed_facts(env):
    # 组合场景:成功 2 + 摘要失败 1 + 重判落选 1 → 正常集合且无残留误占用
    conn = env
    ok1 = _sel_member("ok1"); ok2 = _sel_member("ok2")
    fail = _sel_member("fail", has_summary=False)
    out = compute_final_set([ok1, ok2, fail], overrides={})
    assert [m["identity_key"] for m in out.final] == ["ok1", "ok2"]
    # 落选者本就未 selected(评分失败/门槛)→ 不进集合也无 claim 可残留:
    # 持久化侧由 settle_published 统一清算(验收 4 已锁定)
    for m in (ok1, ok2, fail):
        _seed_entry(conn, identity=m["identity_key"], status="selected",
                    claim="2026-10-06")
    settle_published(conn, "2026-10-06", [ok1["identity_key"],
                                          ok2["identity_key"]])
    n = conn.execute("SELECT COUNT(*) FROM entry WHERE claim_issue IS NOT NULL"
                     " AND status IN ('rejected','failed')").fetchone()[0]
    assert n == 0
    assert conn.execute("SELECT COUNT(*) FROM entry WHERE status='used'"
                        ).fetchone()[0] == 2


# ---------- 验收 9:零合格不产 draft(标志位,文件侧由 Task 16/19 消费) ----------

def test_zero_qualified_flag_drives_no_draft(env):
    conn = env
    low = _analysis_row(conn, _seed_entry(conn), 30, 30)
    result = decide_selection([low], {"T1": 60, "T2": 75}, {})
    assert result.selected == []
    out = compute_final_set(
        [{"identity_key": low["identity_key"], "entry_id": low["entry_id"],
          "source_tier": "T1", "display_score": 30, "force_included": False,
          "has_summary": False, "score_done": True}], overrides={})
    # 全部落选→最终集合空→failed(zero_qualified),调用方不产 draft
    assert out.zero_qualified is True
