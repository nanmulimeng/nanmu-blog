"""URL 判重归一(design.md identity_key 节 R0-R7)。

identity_key = "url:" + 归一后完整 URL(不哈希:可读、可排查、可 LIKE);
entry 与 override 共用该键。entry.url 保留原始 URL 用于展示,不因改键
去请求 https。规则版本变更须先评估 entry/override/回执身份迁移与误合并。
"""

from __future__ import annotations

import urllib.parse

# 追踪参数黑名单(2026-10-04 对照 AIHOT url.ts 定稿;大小写不敏感整名匹配,
# utm_ 为前缀匹配)。反例进强制测试 #1,发现误合并即摘除并记 ADR。
_TRACKING_EXACT = frozenset((
    "fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "_hsenc", "_hsmi",
    "mkt_tok", "spm", "ref", "ref_src", "ref_url", "from", "source",
    "share_source", "share_token", "scene", "chksm", "srcid", "clicktime",
    "enterid", "sessionid",
))

# 微信特判:host 为 mp.weixin.qq.com 时仅保留四参,按此固定顺序重建 query,
# 不参与 R6 排序
_WECHAT_HOST = "mp.weixin.qq.com"
_WECHAT_KEEP_ORDER = ("__biz", "mid", "idx", "sn")


def identity_key(url: str) -> str | None:
    """R0-R7 按序归一;非法输入(scheme 非白名单/端口非法/host 空)
    返回 None,调用方记 invalid 跳过。"""
    try:
        parts = urllib.parse.urlsplit(url.strip())
        port = parts.port          # 端口缺省/非法的探测(非法抛 ValueError)
    except ValueError:
        return None

    # R0:scheme 白名单
    if parts.scheme.lower() not in ("http", "https"):
        return None
    # R1:统一 https、host 小写(仅判重键归一;原始 scheme 留给 R3 用)
    original_scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if not host:
        return None
    # R2:仅去主机名开头的 www.,其余子域保留
    if host.startswith("www."):
        host = host[4:]
    # R3:去**原始** scheme 的默认端口;https:80 等非默认组合保留
    if port is not None and (original_scheme, port) in (("http", 80),
                                                        ("https", 443)):
        port = None

    # R5/R6:query 处理(parse_qsl 保持同名参数原相对顺序,不转 dict 丢值)
    pairs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if host == _WECHAT_HOST:
        kept = [(k, v) for k, v in pairs if k in _WECHAT_KEEP_ORDER]
        pairs = [(name, v) for name in _WECHAT_KEEP_ORDER
                 for k, v in kept if k == name]
    else:
        pairs = [(k, v) for k, v in pairs
                 if k.lower() not in _TRACKING_EXACT
                 and not k.lower().startswith("utm_")]
        pairs = sorted(pairs, key=lambda kv: kv[0])   # 稳定:同名保持原序

    # R7:路径大小写保留;非根路径末尾斜杠去除,根路径保留 /(与 query 无关)
    path = parts.path or "/"
    if len(path) > 1:
        path = path.rstrip("/") or "/"

    netloc = host if port is None else f"{host}:{port}"
    query = urllib.parse.urlencode(pairs)             # 空值保留为 k=
    return "url:" + urllib.parse.urlunsplit(("https", netloc, path, query, ""))
