"""组装与安全输出测试(种子=content-editing 验收 7/8;§3 规则 10;
pipeline.md 产物模板逐项;digest-design §3.1-3.4 样例)。零 LLM。"""

import hashlib
import json
import re
import sqlite3
from pathlib import Path

import pytest

from nanmu_engine.assemble import (
    AssemblyPaused,
    assemble_issue,
    escape_markdown_text,
    safe_source_url,
    write_draft,
)
from nanmu_engine.config import load_config
from nanmu_engine.db import connect_db, migrate

ENGINE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def env(tmp_path):
    conn = connect_db(str(tmp_path / "engine.db"))
    migrate(conn)
    config = load_config(ENGINE_ROOT)
    return conn, config, tmp_path


# ---------- 测试侧渲染管线(mini CommonMark 行内渲染,非字符串比对) ----------

_MD_PUNCT = set(r"\`*_{}[]()#+-.!<>|~")


def render_inline(text: str) -> str:
    """行内渲染子集:反斜杠转义(\\X→字面 X)+ [text](url)→<a>。自由
    文本经 HTML 实体输出(字面 `<` 呈 `&lt;`,不构成标签)。阳性对照见
    test_renderer_detects_unescaped_link。"""
    import html as _html
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text) and text[i + 1] in _MD_PUNCT:
            out.append(_html.escape(text[i + 1]))
            i += 2
            continue
        if ch == "[":
            m = re.match(r"\[([^\]]*)\]\(([^()\s]*)\)", text[i:])
            if m:
                out.append(f'<a href="{_html.escape(m.group(2))}">'
                           f'{_html.escape(m.group(1))}</a>')
                i += m.end()
                continue
        out.append(_html.escape(ch))
        i += 1
    return "".join(out)


def test_renderer_detects_unescaped_link():
    # 阳性对照:渲染器确实识别未转义链接语法(否则"无 <a>"断言无意义)
    assert '<a href="https://e.com">' in render_inline("[x](https://e.com)")
    assert "<a" not in render_inline(r"\[x\](https://e.com)")
    assert "[x](https://e.com)" in render_inline(r"\[x\](https://e.com)")


# ---------- 规则 10:上下文转义与 URL 安全(验收 7) ----------

def test_escape_markdown_text_neutralizes_link_and_script():
    evil = "[伪装链接](https://evil.com) <script>alert(1)</script>"
    esc = escape_markdown_text(evil)
    html = render_inline(esc)
    assert "<a" not in html                      # DOM 无对应 <a>
    # 页面呈字面文本(零宽断链字符不可见,剥除后比对可见内容)
    assert "[伪装链接](https://evil.com)" in html.replace("​", "")
    assert "<script>" not in html                # 字面转义
    assert "alert(1)" in html


def test_escape_strips_control_chars_and_escapes_backslash():
    assert escape_markdown_text("a\x00b\x1fc\x7fd") == "abcd"
    assert render_inline(escape_markdown_text("a\\b")) == "a\\b"
    for ch in "[]()#*_.!`<>{}|~+-":
        assert "\\" + ch in escape_markdown_text(f"x{ch}y")
    # GFM autolink 触发前缀连接点插入零宽字符断自动链接(反斜杠/实体
    # 转义均挡不住,见真实渲染链测试);零宽字符不可见,可见文本不变
    esc = escape_markdown_text("see www.evil.com https://evil.com a@evil.com")
    assert "www​\\.evil\\.com" in esc
    assert "https​://evil\\.com" in esc
    assert "a​@evil\\.com" in esc


def test_escaped_text_blocks_gfm_autolink_in_real_astro_renderer():
    """审计 P2-7:escape 后的裸 URL/www 域名经项目实际安装的 Astro
    Markdown 处理器(@astrojs/markdown-remark,GFM 开)不得产生 <a>,
    且可见文本不变(零宽断链字符不可见,剥除后比对)。不再以自制子集
    渲染器作为该项通过证据。"""
    import json as _json
    import subprocess as _sp

    site = ENGINE_ROOT.parent / "site"
    if not (site / "node_modules" / "@astrojs" / "markdown-remark").exists():
        pytest.skip("site 依赖未安装(site/node_modules)")
    probe = site / ".escape-probe.mjs"
    script = (
        "import {createMarkdownProcessor} from"
        " '@astrojs/markdown-remark';\n"
        "const p = await createMarkdownProcessor({gfm: true});\n"
        "const r = await p.render(JSON.parse(process.argv[2]));\n"
        "console.log(r.code);\n"
    )
    text = "visit https://evil.example.com and www.evil.com"
    try:
        probe.write_text(script, encoding="utf-8")
        r = _sp.run(
            ["node", str(probe), _json.dumps(escape_markdown_text(text))],
            capture_output=True, text=True, encoding="utf-8", cwd=str(site))
        assert r.returncode == 0, r.stderr
        assert "<a" not in r.stdout           # 无任何自动/伪装链接
        visible = r.stdout.replace("​", "")  # 剥不可见零宽字符后可见文本
        assert "evil.example.com" in visible
        assert "www.evil.com" in visible
    finally:
        probe.unlink(missing_ok=True)


def test_safe_source_url_scheme_whitelist_and_encoding():
    assert safe_source_url("https://example.com/a(b) c") == \
        "https://example.com/a%28b%29%20c"
    assert safe_source_url("http://example.com/x") == "http://example.com/x"
    assert safe_source_url("javascript:alert(1)") is None
    assert safe_source_url("data:text/html,x") is None
    assert safe_source_url("") is None


def test_assemble_evil_url_excluded_normal_and_pauses_force(env):
    conn, config, _ = env
    bad = _member("bad", 86, url="javascript:alert(1)")
    ok = _member("ok", 71)
    s = _summary("ok", "ok")
    draft = assemble_issue(config, "2026-10-06", [bad, ok], s, (0.01, False))
    assert "bad" in draft.safety_excluded           # E7 剔除
    assert draft.entry_count == 1

    force_bad = _member("f1", 20, url="javascript:x", force=True)
    with pytest.raises(AssemblyPaused, match="safety"):
        assemble_issue(config, "2026-10-06", [force_bad, ok],
                       _summary("f1", "ok"), (0.01, False))


def test_assemble_model_text_renders_literal(env):
    # 模型输出字段带链接/HTML 语法 → 渲染后全字面,仅来源/标题合法 <a>
    conn, config, _ = env
    members = [_member("m1", 86), _member("m2", 71)]
    s = {
        "m1": {"title_zh": "[伪装链接](https://evil.com)",
               "summary": "<script>alert(1)</script>", "reason": "r",
               "tags": ["t"]},
        **_summary("m2", "m2"),
    }
    draft = assemble_issue(config, "2026-10-06", members, s, (0.11, False))
    body_html = render_inline(draft.markdown)
    assert "evil.com" in body_html                    # 字面文本仍在页面
    assert '<a href="https://evil.com">' not in body_html
    assert "<script>" not in body_html                # &lt;script&gt; 字面
    assert "&lt;script&gt;" in body_html
    # 合法来源链接仍可点(含括号/空白 URL 编码后)
    m3 = _member("m3", 77, url="https://example.com/a(b) c")
    draft3 = assemble_issue(config, "2026-10-06", [m3], _summary("m3", "m3"),
                            (0.01, False))
    html3 = render_inline(draft3.markdown)
    assert '<a href="https://example.com/a%28b%29%20c">' in html3


# ---------- pipeline.md 产物模板逐项(digest-design §3.1 样例) ----------

def _member(key, score, url="https://example.com/x", source="源A",
            force=False, entry_id=None):
    return {"identity_key": key, "entry_id": entry_id or 100,
            "display_score": score, "force_included": force,
            "source_name": source, "url": url}


def _summary(key, title, summary="一句话摘要。", reason="推荐理由。"):
    return {key: {"title_zh": title, "summary": summary,
                  "reason": reason, "tags": ["tag"]}}


def test_assemble_baseline_sample_structure(env):
    conn, config, _ = env
    members = [
        _member("a", 86, url="https://example.com/o5", source="OpenAI Blog"),
        _member("b", 77, url="https://example.com/nano", source="TechCrunch"),
        _member("c", 71, url="https://example.com/attn", source="量子位"),
        _member("d", 20, url="https://example.com/fw", source="HN",
                force=True, entry_id=104),
    ]
    s = {**_summary("a", "头条标题"), **_summary("b", "精选标题"),
         **_summary("c", "一瞥标题"), **_summary("d", "强制标题")}
    draft = assemble_issue(config, "2026-10-06", members, s, (0.11, False))

    fm, _, body = draft.markdown.partition("\n\n")
    assert fm.startswith("---\n") and fm.endswith("---")
    fields = dict(re.findall(r"^(\w+): (.+)$", fm, re.M))
    assert fields["date"] == "'2026-10-06'"
    assert fields["generated"] == "true"
    assert fields["ai_model"] == config.budget.default_model  # 实际模型非示例
    assert fields["entry_count"] == "4"
    assert fields["cost_cny"] == "0.11"
    assert fields["cost_pending"] == "false"               # 显式布尔
    # 板块:头条(86)→精选(77)→一瞥(71+强制 20 末尾带标注)
    assert "## 头条" in body and "### 头条标题" in body
    assert "## 精选" in body and "### 精选标题" in body
    assert "## 值得一瞥" in body
    assert body.index("一瞥标题") < body.index("强制标题")   # 强制恒末尾
    assert "人工纳入" in body and "展示分 20" in body
    assert "> AI 生成与精选 · 模型 " in body and "成本 ¥0.11" in body
    # 头条条目三行结构:标题/摘要/理由+来源链接与展示分
    blk = body[body.index("### 头条标题"):body.index("## 精选")]
    assert "- 一句话摘要。" in blk
    assert "[来源](https://example.com/o5)(OpenAI Blog · 展示分 86)" in blk


def test_assemble_variant_only_glimpse_omits_empty_sections(env):
    conn, config, _ = env
    members = [_member("a", 71), _member("b", 65)]
    draft = assemble_issue(config, "2026-10-06", members,
                           {**_summary("a", "甲"), **_summary("b", "乙")},
                           (0.07, False))
    assert "## 值得一瞥" in draft.markdown
    assert "## 头条" not in draft.markdown      # 不生成空标题凑结构
    assert "## 精选" not in draft.markdown
    assert f"entry_count: {len(members)}" in draft.markdown
    # 板块内展示分降序
    body = draft.markdown
    assert body.index("甲") < body.index("乙")


def test_assemble_cost_pending_annotation(env):
    conn, config, _ = env
    draft = assemble_issue(config, "2026-10-06", [_member("a", 71)],
                           _summary("a", "甲"), (0.12, True))
    assert "cost_pending: true" in draft.markdown
    assert "成本 ¥0.12(含未决预占,为保守上界)" in draft.markdown


# ---------- 落盘协议 + 验收 8(阶段边界:exclude 重组装零费用) ----------

def _attempt_count(conn):
    return conn.execute("SELECT COUNT(*) FROM receipt_attempt").fetchone()[0]


def test_write_draft_persists_file_and_row(env):
    conn, config, tmp = env
    path = tmp / "2026-10-06.md"
    draft = assemble_issue(config, "2026-10-06", [_member("a", 71)],
                           _summary("a", "甲"), (0.07, False))
    sha = write_draft(conn, draft, path)
    assert path.exists()
    assert sha == hashlib.sha256(path.read_bytes()).hexdigest()  # 文件字节
    assert sha == draft.content_sha256
    row = conn.execute(
        "SELECT status, markdown_path, content_sha256, entry_ids, cost_cny"
        " FROM digest_issue WHERE issue_date='2026-10-06'").fetchone()
    assert row[0] == "draft"
    assert row[1] == str(path)
    assert row[2] == sha
    assert json.loads(row[3]) == [100]
    assert row[4] == pytest.approx(0.07)


def test_write_draft_reassemble_updates_same_row(env):
    # 异常 D 幂等:无行→重组装;有行(draft 期)→UPDATE 不重复
    conn, config, tmp = env
    path = tmp / "2026-10-06.md"
    d1 = assemble_issue(config, "2026-10-06", [_member("a", 71)],
                        _summary("a", "甲"), (0.07, False))
    write_draft(conn, d1, path)
    d2 = assemble_issue(config, "2026-10-06",
                        [_member("a", 71), _member("b", 65)],
                        {**_summary("a", "甲"), **_summary("b", "乙")},
                        (0.07, False))
    write_draft(conn, d2, path)
    n = conn.execute("SELECT COUNT(*) FROM digest_issue").fetchone()[0]
    assert n == 1
    assert conn.execute(
        "SELECT content_sha256 FROM digest_issue"
        " WHERE issue_date='2026-10-06'").fetchone()[0] == d2.content_sha256


def test_stage_boundary_exclude_reassembles_zero_cost(env):
    # 验收 8:draft 期 override exclude → 重组装无该条;其余摘要复用零费用
    conn, config, tmp = env
    path = tmp / "2026-10-06.md"
    keep1, keep2, drop = _member("k1", 86), _member("k2", 71), _member("d1", 77)
    members = [keep1, keep2, drop]
    s = {**_summary("k1", "甲"), **_summary("k2", "乙"), **_summary("d1", "丙")}
    before = _attempt_count(conn)
    write_draft(conn, assemble_issue(config, "2026-10-06", members, s,
                                     (0.11, False)), path)
    # override exclude 命中 d1 → 移出最终集合重组装(摘要已付费,复用零新增)
    members2 = [m for m in members if m["identity_key"] != "d1"]
    draft2 = assemble_issue(config, "2026-10-06", members2, s, (0.11, False))
    write_draft(conn, draft2, path)
    after = _attempt_count(conn)
    assert before == after == 0                 # 组装全程零新增网络/付费
    assert "丙" not in path.read_text(encoding="utf-8")
    assert "甲" in path.read_text(encoding="utf-8")
    assert draft2.entry_count == 2
