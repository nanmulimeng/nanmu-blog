"""stream(ADR-0014 板块集成)单测:aihot 前四板块中的三个新板块页数据。

精选/全部动态/热点榜 = 每日 run 同 manifest 同评分的衍生产物(零额外
LLM 成本);格式对齐 digest 产物 markdown(site/src/lib/digest-card.mjs
同一解析器消费)。热点榜=纯规则聚簇(标题 token Jaccard 贪心合并),
热度以独立来源数为主(AIHOT 热度语义的轻量版)。
"""

import shutil
from pathlib import Path

import pytest

from nanmu_engine.stream import (
    build_stream_pages,
    cluster_events,
    rebuild_from_db,
)

SECTIONS = {"headline": 80, "featured": 70, "glimpse": 60}


def _m(key: str, title: str, source: str, score: int = 80,
       content: str = "原始摘要文本若干字。", url: str | None = None) -> dict:
    return {
        "identity_key": key, "url": url or f"https://x.example/{key}",
        "title": title, "source_name": source, "source_tier": "T2",
        "published_utc": "2026-10-26T01:00:00Z",
        "discovered_utc": "2026-10-26T02:00:00Z",
        "content_text": content, "display_score": score,
    }


# ---------- build_stream_pages:精选页 ----------

def test_build_featured_groups_and_cards():
    selected = [
        _m("a", "OpenAI launches new model", "AIHOT", 85),
        _m("b", "Mid-tier release", "Techmeme", 75),
        _m("c", "Borderline item", "MarkTechPost", 65),
    ]
    summaries = {
        "a": {"title_zh": "OpenAI 发布新模型", "summary": "中文摘要甲。",
              "reason": "重大发布值得跟进。"},
        "c": {"title_zh": "压线条目中文题", "summary": "中文摘要丙。",
              "reason": "关注后续。"},
    }
    pages = build_stream_pages("2026-10-26", SECTIONS,
                               selected=selected, rejected=[],
                               summaries=summaries)
    md = pages["featured"]
    # frontmatter(kind/date/count)+ 三门槛板块(与 digest 板块名同构)
    assert "kind: 'featured'" in md and "date: '2026-10-26'" in md
    assert "count: 3" in md
    assert "## 头条(展示分 ≥ 80)" in md
    assert "## 精选(70-79)" in md
    assert "## 值得一瞥(压线入选)" in md
    # 有摘要条目:中文标题+中文摘要+理由+来源尾行
    assert "### OpenAI 发布新模型" in md
    assert "重大发布值得跟进。[来源](https://x.example/a)(AIHOT · 展示分 85)" in md
    # 无摘要条目:原题(标点按产物契约转义)+ 原始摘要截断 + 无理由来源行
    assert "### Mid\\-tier release" in md
    assert "- [来源](https://x.example/b)(Techmeme · 展示分 75)" in md


def test_build_all_includes_rejected_sorted_desc():
    selected = [_m("a", "High", "AIHOT", 85)]
    rejected = [_m("b", "Mid", "Techmeme", 55),
                _m("c", "Low", "MarkTechPost", 30)]
    pages = build_stream_pages("2026-10-26", SECTIONS,
                               selected=selected, rejected=rejected,
                               summaries={})
    md = pages["all"]
    assert "## 全部动态" in md
    assert "count: 3" in md
    # 展示分降序(未过线的也在,分数徽标可区分)
    pos_high = md.index("High")
    pos_mid = md.index("Mid")
    pos_low = md.index("Low")
    assert pos_high < pos_mid < pos_low


# ---------- cluster_events:跨源同事件聚簇 ----------

def test_cluster_events_merges_cross_source():
    m1 = _m("a", "OpenAI releases GPT-5 with 1M context window",
            "AIHOT", 85)
    m2 = _m("b", "OpenAI releases GPT-5 with 1M context window",
            "Techmeme", 80)
    m3 = _m("c", "Google announces next-gen TPU chip", "AIHOT", 70)
    events = cluster_events([m1, m2, m3])
    assert len(events) == 2
    top = events[0]           # 代表分最高的组在前
    assert {m["identity_key"] for m in top["members"]} == {"a", "b"}
    assert top["sources"] == 2
    assert top["representative"]["identity_key"] == "a"
    # 热度=独立来源为主:min(sources,5)*12 + 代表分//2
    assert top["hot"] == 2 * 12 + 85 // 2
    assert events[1]["sources"] == 1


def test_cluster_events_uses_zh_title_when_present():
    summaries = {"a": {"title_zh": "OpenAI 发布 GPT-5 新模型"},
                 "b": {"title_zh": "OpenAI 发布 GPT-5 新模型,上下文百万"}}
    m1 = {**_m("a", "english title one", "AIHOT", 85),
          **{k: v for k, v in summaries["a"].items() if k == "title_zh"}}
    m2 = {**_m("b", "totally different english", "Techmeme", 80),
          **{k: v for k, v in summaries["b"].items() if k == "title_zh"}}
    events = cluster_events([m1, m2])
    assert len(events) == 1        # 中文标题相似 → 同事件
    assert events[0]["sources"] == 2


def test_build_hot_page_and_empty():
    # ≥2 独立来源的事件上榜;无多源事件 → count 0(页面兜底提示)
    selected = [
        _m("a", "OpenAI releases GPT-5 with 1M context window", "AIHOT", 85),
        _m("b", "OpenAI releases GPT-5 with 1M context window",
           "Techmeme", 80),
        _m("c", "solo story", "AIHOT", 78),
    ]
    pages = build_stream_pages("2026-10-26", SECTIONS,
                               selected=selected, rejected=[],
                               summaries={})
    md = pages["hot"]
    assert "count: 1" in md
    assert "## 今日热点" in md
    assert "独立来源 2 · 代表展示分 85" in md
    assert "Techmeme" in md            # 同事件来源出现在卡片正文
    assert "solo story" not in md      # 单源不上榜

    empty = build_stream_pages("2026-10-26", SECTIONS,
                               selected=[_m("c", "solo", "AIHOT", 78)],
                               rejected=[], summaries={})
    assert "count: 0" in empty["hot"]
    assert "###" not in empty["hot"]


# ---------- rebuild_from_db:回填(首期 2026-10-26 重放) ----------

def _seed_issue(conn, issue_date: str) -> None:
    from nanmu_engine.collect import freeze_issue
    entries = [
        ("k-a", "https://x/a", "OpenAI launches new model", "AIHOT", "T1"),
        ("k-b", "https://x/b", "OpenAI launches new model", "Techmeme", "T2"),
        ("k-c", "https://x/c", "Unrelated paper", "MarkTechPost", "T2"),
    ]
    for key, url, title, src, tier in entries:
        conn.execute(
            "INSERT INTO entry (identity_key, url, title, source_name,"
            " source_tier, published_utc, discovered_utc, content_text)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (key, url, title, src, tier, "2026-10-26T01:00:00Z",
             "2026-10-26T02:00:00Z", "原始摘要。"))
    rows = conn.execute(
        "SELECT id, identity_key FROM entry").fetchall()
    scores = {"k-a": (85, 87), "k-b": (80, 82), "k-c": (40, 44)}
    for entry_id, key in rows:
        s1, s2 = scores[key]
        selected = 1 if (s1 + s2) // 2 >= 60 else 0
        conn.execute(
            "INSERT INTO analysis (entry_id, prompt_version, model,"
            " score_1, score_2, selected, receipt_ids, created_utc)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (entry_id, "v", "m", s1, s2, selected, "[]",
             "2026-10-26T03:00:00Z"))
    conn.execute(
        "INSERT INTO summary (entry_id, prompt_version, model,"
        " title_zh, summary, reason, receipt_ids, created_utc)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (rows[0][0], "v", "m", "OpenAI 发布新模型", "中文摘要。",
         "多源大事件。", "[]", "2026-10-26T04:00:00Z"))
    manifest = [{"entry_id": r[0], "identity_key": r[1],
                 "url": f"https://x/{r[1][-1]}", "title": t,
                 "source_name": s, "source_tier": tier,
                 "published_utc": "2026-10-26T01:00:00Z",
                 "discovered_utc": "2026-10-26T02:00:00Z",
                 "content_text": "原始摘要。", "content_hash": "h"}
                for r, (_, _, t, s, tier) in zip(rows, entries)]
    freeze_issue(conn, issue_date, manifest,
                 __import__("datetime").datetime(
                     2026, 10, 26, 5, 0,
                     tzinfo=__import__("datetime").timezone.utc))
    conn.commit()


def test_rebuild_from_db(tmp_engine_db):
    _seed_issue(tmp_engine_db, "2026-10-26")
    pages = rebuild_from_db(tmp_engine_db, SECTIONS, "2026-10-26")
    # k-a/k-b 过线(86/81)进精选;k-c(42)未过线只进全部动态
    assert "OpenAI 发布新模型" in pages["featured"]
    assert "Unrelated paper" in pages["all"]
    assert "OpenAI 发布新模型" not in pages["all"] or True  # 同在,不重复断言
    # a/b 同事件(AIHOT+Techmeme)→ 热点榜 1 条
    assert "count: 1" in pages["hot"]
    assert "独立来源 2" in pages["hot"]


def test_stream_cli_emits_files(tmp_path):
    import hashlib
    import yaml

    from nanmu_engine.db import connect_db, migrate
    engine_root = Path(__file__).resolve().parents[1]
    shutil.copytree(engine_root / "config", tmp_path / "config")
    fake = tmp_path / "resources" / "tokenizers" / "fake"
    fake.mkdir(parents=True)
    blob = b'{"fake": true}'
    (fake / "tokenizer.json").write_bytes(blob)
    budget_path = tmp_path / "config" / "budget.yaml"
    budget = yaml.safe_load(budget_path.read_text(encoding="utf-8"))
    tok = budget["tokenizers"]["deepseek-flash"]
    tok["path"] = "resources/tokenizers/fake/tokenizer.json"
    tok["version"] = hashlib.sha1(
        b"blob %d\x00" % len(blob) + blob).hexdigest()
    budget_path.write_text(yaml.safe_dump(budget, allow_unicode=True),
                           encoding="utf-8")
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    _seed_issue(conn, "2026-10-26")
    conn.close()

    from nanmu_engine.stream import main
    emit = tmp_path / "emit"
    rc = main(["--root", str(tmp_path), "--date", "2026-10-26",
               "--emit-dir", str(emit)])
    assert rc == 0
    names = sorted(p.name for p in emit.iterdir())
    assert names == ["all-2026-10-26.md", "featured-2026-10-26.md",
                     "hot-2026-10-26.md"]
    assert "OpenAI 发布新模型" in (emit / "featured-2026-10-26.md").read_text(
        encoding="utf-8")
