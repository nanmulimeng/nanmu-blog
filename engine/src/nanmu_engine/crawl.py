"""crawl(ADR-0014):AIHOT 爬虫模块(sources/)的 Python/SQLite 移植。

契约来源 KKKKhazix/AIHOT(MIT):
- 读取器三种(rss/web_list/json_list);x_search/mp_account/external 需
  付费 key 或常驻服务端,未落地(扩展位)。
- 键白名单(config-keys.ts):未知配置键=源级失败,不静默回退通用解析。
- 列表准入(filters.ts):前缀过滤 → URL 改写 → 噪声词;publishedAfter
  只收严格晚于且日期可信的条目。
- 调度状态机(collect.ts)在 ingest 侧消费(source_state 表)。

与 AIHOT 的有意差异:summaryIsBody 不落地(本项目管线恒以列表摘要为
content_text,detail 是唯一补齐途径,二元开关无意义)。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote, urljoin
from xml.etree import ElementTree as ET

import httpx


class FetchError(Exception):
    """源级采集失败(单源失败隔离,由调度层计退避,不炸整轮)。"""


class NotModified(Exception):
    """RSS 304:按成功处理,无新增条目,不推进/重置状态。"""


@dataclass(frozen=True)
class SourceSpec:
    """sources.yaml 中 kind 行的运行时形态(对齐 AIHOT SourceRow)。"""
    name: str
    tier: str
    kind: str
    config: dict
    interval_minutes: int = 60
    enabled: bool = True


# 各 kind 认可的配置键(白名单;未知键=unsupported → 源失败)。
_COLLECTED = {
    "allowUrlPrefixes", "denyUrlPrefixes", "itemUrlPrefixRewrite",
    "publishedAfter", "detail", "acceptLanguage", "_aihot",
    "ingestNoiseFilter",
}
_ALLOWED_KEYS: dict[str, set[str]] = {
    "rss": _COLLECTED | {"feedUrl", "publishedAtUtcOffset"},
    "web_list": _COLLECTED | {
        "url", "baseUrl", "parseMode", "itemSelector", "linkSelector",
        "titleSelector", "publishedAtSelector", "publishedAtUtcOffset",
    },
    "json_list": _COLLECTED | {
        "url", "itemsPath", "titlePaths", "summaryPaths",
        "publishedAtPath", "publishedAtUnit", "publishedAtUtcOffset",
        "urlTemplate", "urlTemplateFallback",
    },
}
_DETAIL_KEYS = {
    "maxFetches", "titleSelector", "summarySelector", "publishedAtSelector",
    "publishedAtUtcOffset", "titleAuthoritative", "publishedAtAuthoritative",
}
_REQUIRED_KEYS = {
    "rss": ["feedUrl"],
    "web_list": ["url", "itemSelector"],
    "json_list": ["url", "itemsPath", "titlePaths", "urlTemplate"],
}


def unsupported_config(kind: str, config: dict) -> list[str]:
    """缺失必填键与白名单外键(含 detail 嵌套键);空=配置可用。"""
    allowed = _ALLOWED_KEYS[kind]
    out = [k for k in (config or {}) if k not in allowed]
    for k in _REQUIRED_KEYS[kind]:
        if not (config or {}).get(k):
            out.append(k)
    detail = (config or {}).get("detail")
    if isinstance(detail, dict):
        out += [f"detail.{sub}" for sub in detail if sub not in _DETAIL_KEYS]
    return out


# ---------- 发布时间(dates.ts 简化子集) ----------

_DEFAULT_UTC_OFFSET = "+08:00"   # AIHOT 默认;中文站不例外


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_published(value: Any, *, unit: str | None = None,
                    utc_offset: str | None = None) -> str | None:
    """文本/数字 → 统一 "YYYY-MM-DDTHH:MM:SSZ";不可信返回 None(不猜)。

    支持 RFC822(rss pubDate)、ISO 8601(带偏移/Z/无时区)、纯日期
    (UTC 零点)、epoch_s/epoch_ms/yyyymmdd(json_list unit)。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if unit not in ("epoch_s", "epoch_ms"):
            return None
        try:
            seconds = float(value) / (1 if unit == "epoch_s" else 1000)
            return _iso_z(datetime.fromtimestamp(seconds, tz=timezone.utc))
        except (ValueError, OverflowError, OSError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if unit == "epoch_s" or unit == "epoch_ms":
        try:
            seconds = float(text) / (1 if unit == "epoch_s" else 1000)
            return _iso_z(datetime.fromtimestamp(seconds, tz=timezone.utc))
        except (ValueError, OverflowError, OSError):
            return None
    if unit == "yyyymmdd":
        m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", text)
        if not m:
            return None
        text = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # 纯日期:按 UTC 零点(AIHOT 语义;无时分可谈偏移)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return _iso_z(datetime.strptime(text, "%Y-%m-%d")
                          .replace(tzinfo=timezone.utc))
        except ValueError:
            return None
    # RFC822(pubDate)
    if re.match(r"^[A-Za-z]{3},", text):
        try:
            dt = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
        return _iso_z(dt) if dt is not None else None
    # ISO 8601:补默认时区后 fromisoformat(Python 3.11 认 Z)
    iso = text.replace("Z", "+00:00") if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if dt.tzinfo is None:
        offset = utc_offset or _DEFAULT_UTC_OFFSET
        try:
            sign = 1 if offset[0] == "+" else -1
            delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[4:6]))
        except (ValueError, IndexError):
            return None
        dt = dt.replace(tzinfo=timezone(sign * delta))
    return _iso_z(dt)


# ---------- 列表准入(filters.ts:前缀 → 改写 → 噪声) ----------

def _allowed_by_prefixes(url: str, config: dict) -> bool:
    deny = config.get("denyUrlPrefixes") or []
    if any(url.startswith(p) for p in deny):
        return False
    allow = config.get("allowUrlPrefixes")
    if not allow:
        return True
    return any(url.startswith(p) for p in allow)


def _rewrite_url(url: str, config: dict) -> str:
    rw = config.get("itemUrlPrefixRewrite") or {}
    src, dst = rw.get("from"), rw.get("to")
    if src and dst and url.startswith(src):
        return dst + url[len(src):]
    return url


def _noise_filtered(cand: dict, config: dict) -> bool:
    f = config.get("ingestNoiseFilter")
    if not f:
        return False
    title = (cand.get("title") or "").lower()
    hay = f"{title}\n{(cand.get('content_text') or '').lower()}"
    if any(k.lower() in hay for k in f.get("keepIfMatches", [])):
        return False
    if any(k.lower() in title for k in f.get("dropMarkersTitleOnly", [])):
        return True
    return any(k.lower() in hay for k in f.get("dropMarkers", []))


def admit_listing(candidates: list[dict], spec: SourceSpec) -> list[dict]:
    """前缀准入 → URL 改写 → 噪声剔除;输出新列表(不改入参元素)。"""
    kept = []
    for c in candidates:
        if not _allowed_by_prefixes(c.get("url", ""), spec.config):
            continue
        c = {**c, "url": _rewrite_url(c["url"], spec.config)}
        if _noise_filtered(c, spec.config):
            continue
        kept.append(c)
    return kept


def filter_publication_window(candidates: list[dict],
                              spec: SourceSpec) -> list[dict]:
    """publishedAfter:只收严格晚于起点且日期可信的条目;未配置=原样。"""
    after = spec.config.get("publishedAfter")
    if not after:
        return list(candidates)
    return [c for c in candidates
            if c.get("published_utc") and c["published_utc"] > after]


# ---------- HTTP(测试注入点;真实实现 httpx 直连) ----------

_UA = "nanmu-blog-engine/1.0"
_TAG_RE = re.compile(r"<[^>]+>")


def _http_get(url: str, *, headers: dict | None = None,
              timeout: float = 30.0):
    return httpx.get(url, timeout=timeout, follow_redirects=True,
                     headers={"User-Agent": _UA, **(headers or {})})


def _strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", html or "")).strip()


def _require_ok(resp) -> None:
    if resp.status_code == 304:
        raise NotModified()
    if resp.status_code >= 400:
        raise FetchError(f"http {resp.status_code}: {resp.url}")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_child(entry, *names: str):
    for child in entry:
        if _local(child.tag) in names:
            return child
    return None


def _child_text(entry, *names: str) -> str:
    node = _first_child(entry, *names)
    return (node.text or "").strip() if node is not None else ""


# ---------- rss(RSS <item> + Atom <entry>;ETag/Last-Modified validator) ----------

def fetch_rss(spec: SourceSpec,
              state: dict) -> tuple[list[dict], str | None, str | None]:
    """feed → (候选列表, etag, last_modified)。304 → NotModified。"""
    headers: dict[str, str] = {}
    if state.get("etag"):
        headers["If-None-Match"] = state["etag"]
    if state.get("last_modified"):
        headers["If-Modified-Since"] = state["last_modified"]
    resp = _http_get(spec.config["feedUrl"], headers=headers or None)
    _require_ok(resp)
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError as exc:
        raise FetchError(f"feed 解析失败: {exc}") from exc
    utc_offset = spec.config.get("publishedAtUtcOffset")
    out: list[dict] = []
    if _local(root.tag) == "feed":       # Atom
        for entry in root:
            if _local(entry.tag) != "entry":
                continue
            link = ""
            for child in entry:
                if _local(child.tag) != "link":
                    continue
                rel = child.get("rel", "alternate")
                if rel == "alternate" and child.get("href"):
                    link = child.get("href", "").strip()
                    break
            published = _child_text(entry, "published", "updated", "pubDate")
            out.append({
                "url": link,
                "title": _child_text(entry, "title"),
                "published_utc": parse_published(published,
                                                 utc_offset=utc_offset),
                "content_text": _strip_tags(_child_text(
                    entry, "summary", "content", "description")),
            })
    else:                                 # RSS 2.0
        for item in root.iter("item"):
            pub = _child_text(item, "pubDate", "published")
            out.append({
                "url": _child_text(item, "link", "guid"),
                "title": _child_text(item, "title"),
                "published_utc": parse_published(pub,
                                                 utc_offset=utc_offset),
                "content_text": _strip_tags(_child_text(
                    item, "description", "encoded", "summary")),
            })
    return ([c for c in out if c["url"]],
            resp.headers.get("ETag"), resp.headers.get("Last-Modified"))


# ---------- web_list(CSS 选择器;detail 补齐) ----------

def _full_text(soup) -> str:
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ")).strip()[:4000]


def _node_date(node, utc_offset) -> str | None:
    if node is None:
        return None
    raw = (node.get("datetime") or node.get("content")
           or node.get("title") or node.get_text(" "))
    return parse_published(raw, utc_offset=utc_offset)


def _fetch_detail(cand: dict, detail: dict) -> None:
    """详情页补齐(summarySelector 优先,无则全文提取;失败跳过等下轮)。"""
    from bs4 import BeautifulSoup
    try:
        resp = _http_get(cand["url"])
        _require_ok(resp)
    except (FetchError, NotModified):
        return
    soup = BeautifulSoup(resp.text, "html.parser")
    sel = detail.get("summarySelector")
    if sel:
        node = soup.select_one(sel)
        text = re.sub(r"\s+", " ", node.get_text(" ")).strip() \
            if node is not None else ""
    else:
        text = _full_text(soup)
    if text:
        cand["content_text"] = text
    if not cand.get("published_utc") and detail.get("publishedAtSelector"):
        cand["published_utc"] = _node_date(
            soup.select_one(detail["publishedAtSelector"]),
            detail.get("publishedAtUtcOffset"))
    if detail.get("titleSelector") and (
            detail.get("titleAuthoritative") or not cand.get("title")):
        node = soup.select_one(detail["titleSelector"])
        if node is not None:
            cand["title"] = node.get_text(" ").strip()


def _enrich_details(cands: list[dict], config: dict) -> None:
    """detail.maxFetches 预算内,为缺日期或缺正文的条目抓详情页。"""
    detail = config.get("detail") or {}
    budget = int(detail.get("maxFetches") or 0)
    if budget <= 0:
        return
    for cand in cands:
        if budget <= 0:
            break
        if cand.get("published_utc") and cand.get("content_text"):
            continue
        budget -= 1
        _fetch_detail(cand, detail)


def fetch_web_list(spec: SourceSpec) -> list[dict]:
    from bs4 import BeautifulSoup

    cfg = spec.config
    if cfg.get("parseMode", "html") != "html":
        raise FetchError(
            f"parseMode 仅支持 html(得到 {cfg.get('parseMode')!r};"
            "markdown/docusaurus_changelog/intercom_changelog 未落地)")
    resp = _http_get(cfg["url"])
    _require_ok(resp)
    soup = BeautifulSoup(resp.text, "html.parser")
    base = cfg.get("baseUrl") or str(resp.url)
    listing_url = str(resp.url)
    utc_offset = cfg.get("publishedAtUtcOffset")
    items = soup.select(cfg["itemSelector"])
    if not items:
        raise FetchError("no items matched (html)")
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        link_node = (item.select_one(cfg["linkSelector"])
                     if cfg.get("linkSelector") else None)
        if link_node is None and item.name == "a":
            link_node = item
        if link_node is None or not link_node.get("href"):
            continue
        url = urljoin(base, link_node["href"].strip())
        if url == listing_url or url in seen:
            continue
        seen.add(url)
        title_node = (item.select_one(cfg["titleSelector"])
                      if cfg.get("titleSelector") else None)
        title = (title_node.get_text(" ") if title_node is not None
                 else link_node.get_text(" "))
        out.append({
            "url": url,
            "title": re.sub(r"\s+", " ", title).strip(),
            "published_utc": _node_date(
                item.select_one(cfg["publishedAtSelector"])
                if cfg.get("publishedAtSelector") else None, utc_offset),
            "content_text": "",
        })
    _enrich_details(out, cfg)
    return out


# ---------- json_list(字段路径映射;json-list.ts 核心子集) ----------

def _get_path(obj, path: str):
    cur = obj
    for seg in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list) and seg.isdigit():
            cur = cur[int(seg)]
        elif isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
    return cur


def _first_string(item, paths) -> str:
    for p in paths or []:
        v = _get_path(item, p)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)
    return ""


def _render_template(template: str, item) -> str:
    """{path} URL 编码(斜杠还原)/{raw:path} 原样。"""
    def _sub(m):
        raw, path = m.group(1), m.group(2)
        v = _get_path(item, path)
        if v is None or v == "":
            return ""
        return str(v) if raw else quote(str(v), safe="").replace("%2F", "/")
    return re.sub(r"\{(raw:)?([^}]+)\}", _sub, template)


def fetch_json_list(spec: SourceSpec) -> list[dict]:
    import json

    cfg = spec.config
    resp = _http_get(cfg["url"])
    _require_ok(resp)
    try:
        data = json.loads(resp.text)
    except json.JSONDecodeError as exc:
        raise FetchError(f"response is not JSON: {exc}") from exc
    items = _get_path(data, cfg["itemsPath"]) if cfg.get("itemsPath") else data
    if not isinstance(items, list):
        raise FetchError("items path did not resolve to an array")
    unit = cfg.get("publishedAtUnit")
    utc_offset = cfg.get("publishedAtUtcOffset")
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = _first_string(item, cfg.get("titlePaths"))
        url = (_render_template(cfg["urlTemplate"], item)
               if cfg.get("urlTemplate") else "")
        if not url and cfg.get("urlTemplateFallback"):
            url = _render_template(cfg["urlTemplateFallback"], item)
        if not title or not url.startswith(("http://", "https://")):
            continue
        out.append({
            "url": url,
            "title": _strip_tags(title),
            "published_utc": parse_published(
                _get_path(item, cfg.get("publishedAtPath", "")),
                unit=unit, utc_offset=utc_offset),
            "content_text": _strip_tags(
                _first_string(item, cfg.get("summaryPaths"))),
        })
    if items and not out:
        raise FetchError("no items mapped (check title/url paths)")
    _enrich_details(out, cfg)
    return out


# ---------- 调度分发入口(ingest 消费) ----------

def fetch_listing(spec: SourceSpec, state: dict) -> tuple[list[dict], dict]:
    """配置门禁 + 按 kind 分发;返回(候选, validator)。

    validator 仅 rss 产生({"etag","last_modified"},store 成功后由
    调度层写回 source_state)。
    """
    if spec.kind not in _ALLOWED_KEYS:
        raise FetchError(f"kind 未落地: {spec.kind}"
                         "(x_search/mp_account/external 需付费 key 或常驻服务端)")
    bad = unsupported_config(spec.kind, spec.config)
    if bad:
        raise FetchError(f"unsupported config: {', '.join(bad)}")
    if spec.kind == "rss":
        cands, etag, last_mod = fetch_rss(spec, state)
        _enrich_details(cands, spec.config)
        return cands, {"etag": etag, "last_modified": last_mod}
    if spec.kind == "web_list":
        return fetch_web_list(spec), {}
    if spec.kind == "json_list":
        return fetch_json_list(spec), {}
    raise FetchError(f"kind 未落地: {spec.kind}"
                     "(x_search/mp_account/external 需付费 key 或常驻服务端)")
