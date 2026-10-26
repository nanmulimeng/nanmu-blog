"""crawl(ADR-0014)单测:AIHOT sources/ 模块的 Python 移植。

契约对齐 KKKKhazix/AIHOT(读取器语义见 docs/sources.md;键白名单见
config-keys.ts)。HTTP 一律注入/monkeypatch,不访问网络。
"""

import json as _json

import pytest

from nanmu_engine.crawl import (
    SourceSpec,
    admit_listing,
    filter_publication_window,
    parse_published,
    unsupported_config,
)


def _spec(kind: str, config: dict, **kw) -> SourceSpec:
    return SourceSpec(name="t", tier="T2", kind=kind, config=config, **kw)


# ---------- 配置键白名单(config-keys.ts:未知键=源级失败,不静默回退) ----------

def test_unsupported_config_lists_unknown_keys():
    spec = _spec("rss", {"feedUrl": "https://x/feed", "adapter": "site_cards"})
    assert unsupported_config(spec.kind, spec.config) == ["adapter"]
    # 各 kind 认可的专属键
    assert unsupported_config("web_list", {
        "url": "u", "itemSelector": ".i", "linkSelector": "a",
        "titleSelector": "a", "publishedAtSelector": "time",
        "baseUrl": "https://x/", "parseMode": "html",
    }) == []
    assert unsupported_config("json_list", {
        "url": "u", "itemsPath": "data.items", "titlePaths": ["title"],
        "urlTemplate": "{raw:url}", "summaryPaths": ["summary"],
        "publishedAtPath": "published_at", "publishedAtUnit": "epoch_s",
    }) == []
    # 通用 COLLECTED 键全 kind 认可(附各自必填键)
    common = {"allowUrlPrefixes": ["https://x/"], "denyUrlPrefixes": [],
              "itemUrlPrefixRewrite": {"from": "a", "to": "b"},
              "publishedAfter": "2026-10-01T00:00:00Z",
              "detail": {"maxFetches": 2}, "acceptLanguage": "en-US,en;q=0.9"}
    required = {"rss": {"feedUrl": "u"},
                "web_list": {"url": "u", "itemSelector": ".i"},
                "json_list": {"url": "u", "itemsPath": "d",
                              "titlePaths": ["t"], "urlTemplate": "{raw:url}"}}
    for kind in ("rss", "web_list", "json_list"):
        assert unsupported_config(kind, {**common, **required[kind]}) == []
    # 嵌套键校验:detail 只认子集
    assert unsupported_config(
        "rss", {"feedUrl": "u", "detail": {"maxFetches": 1, "foo": 1}}
    ) == ["detail.foo"]
    # 未落地键:summaryIsBody(本项目管线恒以摘要为正文,detail 是唯一补齐)
    assert unsupported_config("rss", {"feedUrl": "u", "summaryIsBody": True}) \
        == ["summaryIsBody"]


def test_required_keys_reported_as_unsupported():
    assert unsupported_config("rss", {}) == ["feedUrl"]
    assert unsupported_config("web_list", {}) == ["url", "itemSelector"]
    assert unsupported_config("json_list", {}) == [
        "url", "itemsPath", "titlePaths", "urlTemplate"]


# ---------- 发布时间解析(dates.ts 简化:ISO/RFC822/epoch/yyyymmdd) ----------

def test_parse_published_variants():
    # RFC822(带时区)
    assert parse_published("Mon, 26 Oct 2026 08:00:00 GMT") \
        == "2026-10-26T08:00:00Z"
    # ISO 带 Z/偏移
    assert parse_published("2026-10-26T16:00:00+08:00") \
        == "2026-10-26T08:00:00Z"
    # 无时区 → 默认 +08:00
    assert parse_published("2026-10-26 16:00:00") == "2026-10-26T08:00:00Z"
    assert parse_published("2026-10-26 16:00:00", utc_offset="-05:00") \
        == "2026-10-26T21:00:00Z"
    # 纯日期按 UTC 零点(AIHOT 语义)
    assert parse_published("2026-10-26") == "2026-10-26T00:00:00Z"
    # epoch 单位
    from datetime import datetime as _dt, timezone as _tz
    epoch = int(_dt(2026, 10, 26, tzinfo=_tz.utc).timestamp())
    assert parse_published(str(epoch), unit="epoch_s") \
        == "2026-10-26T00:00:00Z"
    assert parse_published(str(epoch * 1000), unit="epoch_ms") \
        == "2026-10-26T00:00:00Z"
    # yyyymmdd
    assert parse_published("20261026", unit="yyyymmdd") \
        == "2026-10-26T00:00:00Z"
    # 坏值/空 → None(不猜)
    assert parse_published("next Tuesday") is None
    assert parse_published("") is None
    assert parse_published(None) is None


# ---------- 列表准入过滤(filters.ts:前缀→改写→噪声) ----------

def _cand(url: str, title="t", published=None, excerpt=""):
    return {"url": url, "title": title, "published_utc": published,
            "content_text": excerpt}


def test_admit_listing_prefix_rewrite_noise():
    spec = _spec("rss", {
        "feedUrl": "u",
        "allowUrlPrefixes": ["https://x.com/posts/"],
        "denyUrlPrefixes": ["https://x.com/posts/sponsor/"],
        "itemUrlPrefixRewrite": {"from": "https://x.com/",
                                 "to": "https://mirror.example/"},
        "ingestNoiseFilter": {
            "dropMarkers": ["sponsored"],
            "dropMarkersTitleOnly": ["newsletter"],
            "keepIfMatches": ["openai"],
        },
    })
    cands = [
        _cand("https://x.com/posts/a"),                          # 留
        _cand("https://x.com/posts/sponsor/b"),                  # deny
        _cand("https://elsewhere.example/c"),                    # 非 allow
        _cand("https://x.com/posts/n", title="Weekly Newsletter #1"),  # 标题噪声
        _cand("https://x.com/posts/s", title="Sponsored post"),  # 全文噪声
        _cand("https://x.com/posts/o", title="Sponsored post",
              excerpt="openai released..."),                     # 豁免词保住
    ]
    kept = admit_listing(cands, spec)
    urls = [c["url"] for c in kept]
    # 改写在准入后:留下的地址换前缀
    assert urls == ["https://mirror.example/posts/a",
                    "https://mirror.example/posts/o"]


def test_filter_publication_window_strictly_after():
    spec = _spec("rss", {"feedUrl": "u",
                         "publishedAfter": "2026-10-01T00:00:00Z"})
    cands = [
        _cand("a", published="2026-10-02T00:00:00Z"),   # 留(严格晚于)
        _cand("b", published="2026-10-01T00:00:00Z"),   # 等于=不留
        _cand("c", published="2026-09-01T00:00:00Z"),   # 早于
        _cand("d", published=None),                     # 未知日期不留
    ]
    assert [c["url"] for c in filter_publication_window(cands, spec)] == ["a"]
    # 无 publishedAfter → 原样(日期未知交给入库侧 staleness 规则)
    assert len(filter_publication_window(cands, _spec("rss", {"feedUrl": "u"}))) == 4


# ---------- 读取器(HTTP 一律 monkeypatch crawl._http_get) ----------

class _StubResp:
    def __init__(self, text="", status=200, headers=None, url=""):
        self.text = text
        self.status_code = status
        self.headers = headers or {}
        self.url = url


@pytest.fixture()
def http(monkeypatch):
    """按 URL 前缀路由的假 HTTP;记录请求头供断言。"""
    served: dict[str, _StubResp] = {}
    seen: list[dict] = []

    def _get(url, *, headers=None, timeout=30.0):
        seen.append({"url": url, "headers": headers or {}})
        for prefix, resp in served.items():
            if url.startswith(prefix):
                return resp
        return _StubResp("not found", status=404, url=url)

    import nanmu_engine.crawl as crawl
    monkeypatch.setattr(crawl, "_http_get", _get)
    return {"served": served, "seen": seen}


RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>Post A</title><link>https://x.example/a</link>
<pubDate>Mon, 26 Oct 2026 08:00:00 GMT</pubDate>
<description>&lt;p&gt;正文甲&lt;/p&gt;</description></item>
<item><title>Post B</title><link>https://x.example/b</link>
<description>无日期条目</description></item>
</channel></rss>"""

ATOM_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom 项</title>
<link rel="alternate" href="https://x.example/atom-1"/>
<published>2026-10-26T02:00:00Z</published>
<summary>Atom 摘要</summary></entry>
</feed>"""


def test_fetch_rss_rss_and_atom_and_304(http):
    import nanmu_engine.crawl as crawl
    http["served"]["https://x.example/feed"] = _StubResp(
        RSS_XML,
        headers={"ETag": '"v1"',
                 "Last-Modified": "Tue, 27 Oct 2026 00:00:00 GMT"},
        url="https://x.example/feed")
    spec = _spec("rss", {"feedUrl": "https://x.example/feed"})
    cands, etag, last_mod = crawl.fetch_rss(spec, {})
    assert [c["title"] for c in cands] == ["Post A", "Post B"]
    assert cands[0]["url"] == "https://x.example/a"
    assert cands[0]["published_utc"] == "2026-10-26T08:00:00Z"
    assert cands[0]["content_text"] == "正文甲"
    assert cands[1]["published_utc"] is None
    assert etag == '"v1"'
    assert last_mod == "Tue, 27 Oct 2026 00:00:00 GMT"
    # 带状态回传 validator → 服务器 304 → NotModified(成功无新增)
    http["served"]["https://x.example/feed"] = _StubResp(
        "", status=304, url="https://x.example/feed")
    with pytest.raises(crawl.NotModified):
        crawl.fetch_rss(spec, {"etag": '"v1"',
                               "last_modified": "Tue, 27 Oct 2026 00:00:00 GMT"})
    assert http["seen"][-1]["headers"].get("If-None-Match") == '"v1"'

    # Atom:entry/link[@href]/published/summary
    http["served"]["https://x.example/atom"] = _StubResp(
        ATOM_XML, url="https://x.example/atom")
    cands2, _, _ = crawl.fetch_rss(
        _spec("rss", {"feedUrl": "https://x.example/atom"}), {})
    assert len(cands2) == 1
    assert cands2[0]["url"] == "https://x.example/atom-1"
    assert cands2[0]["published_utc"] == "2026-10-26T02:00:00Z"
    assert cands2[0]["content_text"] == "Atom 摘要"


WEB_HTML = """<html><body><div class="news-list">
<div class="news-item"><h2><a href="/posts/first">第一条</a></h2>
<time datetime="2026-10-01T09:00:00+08:00">10 月 1 日</time></div>
<div class="news-item"><h2><a href="https://x.example/posts/second">第二条</a></h2>
<time>not a date</time></div>
<div class="news-item"><h2><a href="https://x.example/news">指向列表自身</a></h2></div>
<div class="news-item"><h2><a href="/posts/first">重复链接</a></h2></div>
</div></body></html>"""


def test_fetch_web_list_selectors_relative_links_dedup(http):
    import nanmu_engine.crawl as crawl
    http["served"]["https://x.example/news"] = _StubResp(
        WEB_HTML, url="https://x.example/news")
    spec = _spec("web_list", {
        "url": "https://x.example/news",
        "itemSelector": ".news-list > .news-item",
        "linkSelector": "h2 a", "titleSelector": "h2 a",
        "publishedAtSelector": "time"})
    cands = crawl.fetch_web_list(spec)
    # 相对链接按最终地址解析;列表自身链接跳过;重复链接合并(首现)
    assert [c["url"] for c in cands] == [
        "https://x.example/posts/first", "https://x.example/posts/second"]
    assert cands[0]["published_utc"] == "2026-10-01T01:00:00Z"
    assert cands[1]["published_utc"] is None    # 无效日期文字不猜
    assert cands[0]["title"] == "第一条"
    # 容器选择器(选到包裹层)只出一条——文档对照语义
    bad = _spec("web_list", {**spec.config,
                             "itemSelector": ".news-list"})
    assert len(crawl.fetch_web_list(bad)) == 1


def test_fetch_web_list_parse_mode_and_detail(http):
    import nanmu_engine.crawl as crawl
    spec_cfg = {
        "url": "https://x.example/news",
        "itemSelector": ".news-item", "linkSelector": "h2 a",
        "titleSelector": "h2 a",
        "parseMode": "markdown"}   # 仅 html 落地
    with pytest.raises(crawl.FetchError, match="parseMode"):
        crawl.fetch_web_list(_spec("web_list", spec_cfg))

    # detail:列表缺摘要 → 抓详情页补(summarySelector 优先,无则全文)
    http["served"]["https://x.example/news"] = _StubResp(
        WEB_HTML, url="https://x.example/news")
    http["served"]["https://x.example/posts/"] = _StubResp(
        """<html><body><article><h1>第一条</h1>
        <p class="lead">详情页导语。</p><p>正文段落。</p></article></body></html>""",
        url="https://x.example/posts/first")
    spec = _spec("web_list", {
        "url": "https://x.example/news",
        "itemSelector": ".news-list > .news-item",
        "linkSelector": "h2 a", "titleSelector": "h2 a",
        "publishedAtSelector": "time",
        "detail": {"maxFetches": 1, "summarySelector": "p.lead"}})
    cands = crawl.fetch_web_list(spec)
    first = next(c for c in cands if c["url"].endswith("/posts/first"))
    assert first["content_text"] == "详情页导语。"
    # maxFetches=1:第二条未获详情页预算
    second = next(c for c in cands if c["url"].endswith("/posts/second"))
    assert second["content_text"] == ""
    # 无 summarySelector:全文提取(去脚本样式、折叠空白、截断)
    http["served"]["https://x.example/posts/"] = _StubResp(
        """<html><head><style>.a{}</style></head><body>
        <script>var x=1;</script><p>段一。</p><p>段二。</p></body></html>""",
        url="https://x.example/posts/first")
    spec2 = _spec("web_list", {**spec.config,
                               "detail": {"maxFetches": 1}})
    cands2 = crawl.fetch_web_list(spec2)
    first2 = next(c for c in cands2 if c["url"].endswith("/posts/first"))
    assert first2["content_text"] == "段一。 段二。"


JSON_BODY = {
    "data": {"items": [
        {"id": "first", "title": "第一条",
         "url": "https://x.example/posts/first",
         "summary": "摘要一。",
         "published_at": "2026-10-01T09:00:00+08:00"},
        {"id": "second", "title": "第二条", "slug": "second",
         "published_at": 1793500800, "draft": True},
    ]}}


def test_fetch_json_list_mapping(http):
    import nanmu_engine.crawl as crawl
    http["served"]["https://x.example/api"] = _StubResp(
        _json.dumps(JSON_BODY), url="https://x.example/api")
    spec = _spec("json_list", {
        "url": "https://x.example/api", "itemsPath": "data.items",
        "titlePaths": ["title", "name"],
        "urlTemplate": "{raw:url}",
        "urlTemplateFallback": "https://x.example/p/{slug}",
        "summaryPaths": ["summary"],
        "publishedAtPath": "published_at"})
    cands = crawl.fetch_json_list(spec)
    assert [c["title"] for c in cands] == ["第一条", "第二条"]
    assert cands[0]["url"] == "https://x.example/posts/first"
    assert cands[1]["url"] == "https://x.example/p/second"
    assert cands[0]["content_text"] == "摘要一。"
    assert cands[1]["content_text"] == ""
    assert cands[0]["published_utc"] == "2026-10-01T01:00:00Z"


def test_fetch_json_list_errors(http):
    import nanmu_engine.crawl as crawl
    # itemsPath 不是数组
    http["served"]["https://x.example/api"] = _StubResp(
        _json.dumps({"data": {"items": 5}}), url="https://x.example/api")
    spec = _spec("json_list", {
        "url": "https://x.example/api", "itemsPath": "data.items",
        "titlePaths": ["title"], "urlTemplate": "{raw:url}"})
    with pytest.raises(crawl.FetchError, match="items path"):
        crawl.fetch_json_list(spec)
    # 非空数组全映射失败(路径错)
    http["served"]["https://x.example/api"] = _StubResp(
        _json.dumps([{"name": "只有 name"}]), url="https://x.example/api")
    spec2 = _spec("json_list", {
        "url": "https://x.example/api",
        "titlePaths": ["title"], "urlTemplate": "{raw:url}"})
    with pytest.raises(crawl.FetchError, match="no items mapped"):
        crawl.fetch_json_list(spec2)


def test_fetch_listing_dispatch_and_config_gate(http):
    import nanmu_engine.crawl as crawl
    # 未知配置键 → 源级 FetchError(不静默回退)
    bad = _spec("rss", {"feedUrl": "https://x/feed", "adapter": "x"})
    with pytest.raises(crawl.FetchError, match="unsupported config"):
        crawl.fetch_listing(bad, {})
    # 非落地 kind
    with pytest.raises(crawl.FetchError, match="kind"):
        crawl.fetch_listing(_spec("x_search", {"query": "from:a"}), {})
    # rss 正常分发
    http["served"]["https://x.example/feed"] = _StubResp(
        RSS_XML, url="https://x.example/feed")
    out = crawl.fetch_listing(
        _spec("rss", {"feedUrl": "https://x.example/feed"}), {})
    assert len(out) == 2
