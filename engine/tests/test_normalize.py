"""normalize 判重归一测试(种子=design.md identity_key 节 R0-R7 + 五行期望表;
夹具与 design.md 共享,规则版本变更须先评估迁移)。"""

import pytest

from nanmu_engine.normalize import identity_key

# design.md 期望表逐条断言(强制测试 #1 用例族)
DESIGN_TABLE = [
    ("http://WWW.Example.com:80/A/?b=2&a=1#part",
     "url:https://example.com/A?a=1&b=2"),
    ("https://example.com:80/A/", "url:https://example.com:80/A"),
    ("https://example.com/", "url:https://example.com/"),
    ("https://example.com/a/?b=2&utm_source=x",
     "url:https://example.com/a?b=2"),
    ("https://mp.weixin.qq.com/s?sn=d&idx=1&mid=b&__biz=a&scene=2",
     "url:https://mp.weixin.qq.com/s?__biz=a&mid=b&idx=1&sn=d"),
]


@pytest.mark.parametrize("url,expected", DESIGN_TABLE)
def test_design_table(url, expected):
    assert identity_key(url) == expected


def test_r0_non_http_scheme_invalid():
    assert identity_key("ftp://example.com/a") is None
    assert identity_key("javascript:alert(1)") is None
    assert identity_key("mailto:x@y.z") is None


def test_invalid_port_or_host():
    assert identity_key("https://example.com:99999/") is None   # 端口越界
    assert identity_key("https://example.com:port/") is None    # 端口非数字
    assert identity_key("https:///path") is None                # 空 host


def test_tracking_params_removed_case_insensitive():
    assert identity_key("https://e.com/a?FBCLID=x&GCLID=y&b=1") \
        == "url:https://e.com/a?b=1"


def test_blacklist_whole_name_match_only():
    # 整名匹配:ref 在黑名单而 referrer 不在——业务参数反例不误伤
    assert identity_key("https://e.com/a?referrer=x&ref=y") \
        == "url:https://e.com/a?referrer=x"


def test_wechat_only_four_params_kept():
    # 微信特判:仅四参保留,其余(含非黑名单参数)一律去除
    assert identity_key("https://mp.weixin.qq.com/s?mid=b&foo=1") \
        == "url:https://mp.weixin.qq.com/s?mid=b"
    # 四参顺序固定重建,不受输入顺序影响
    a = identity_key("https://mp.weixin.qq.com/s?sn=d&__biz=a")
    b = identity_key("https://mp.weixin.qq.com/s?__biz=a&sn=d")
    assert a == b == "url:https://mp.weixin.qq.com/s?__biz=a&sn=d"


def test_duplicate_params_keep_relative_order():
    # 同名参数保持原相对顺序,不得转 dict 丢值
    assert identity_key("https://e.com/?b=2&b=1&a=1") \
        == "url:https://e.com/?a=1&b=2&b=1"


def test_unicode_query_decodes_and_reencodes_stable():
    # query:原文 Unicode 与百分号编码 → 同 key,序列化固定为编码形式
    assert identity_key("https://e.com/?q=中文") \
        == identity_key("https://e.com/?q=%E4%B8%AD%E6%96%87") \
        == "url:https://e.com/?q=%E4%B8%AD%E6%96%87"


def test_empty_value_and_empty_path():
    assert identity_key("https://e.com/a?b=&a=1") == "url:https://e.com/a?a=1&b="
    assert identity_key("https://e.com") == "url:https://e.com/"


def test_root_path_slash_kept_with_query():
    assert identity_key("https://e.com/?a=1") == "url:https://e.com/?a=1"


def test_path_case_preserved_and_trailing_slash_only_nonroot():
    assert identity_key("https://e.com/Aa/Bb/") == "url:https://e.com/Aa/Bb"
    assert identity_key("https://e.com/Aa/Bb/?x=1") == "url:https://e.com/Aa/Bb?x=1"


def test_determinism_all_table_cases_repeatable():
    for url, expected in DESIGN_TABLE:
        assert identity_key(url) == identity_key(url) == expected
