"""token_count 单元测试。

种子:计划 Task 1 Step 2 = units/content-editing.md §7 场景 3 前半 +
units/model-calls.md §3 规则 2(计数对象=完整请求消息数组;计数不可得
→不出网,不回退字符估算)。
"""

import pytest

from nanmu_engine.token_count import (
    TokenizerUnavailable,
    count_request_tokens,
    load_tokenizer,
)

M = "deepseek-flash"
SYS = "你是评分器,只输出 JSON。"
TEXT = "工具教程:一款静态站点生成器的入门配置,涵盖安装、路由与部署。"
MSGS = [
    {"role": "system", "content": SYS},
    {"role": "user", "content": TEXT},
]


def test_count_covers_message_structure_not_just_text():
    # 同一段文本,裸字符串计数 < 完整 messages 结构计数(结构开销必须计入)
    bare = len(load_tokenizer(M).encode(TEXT, add_special_tokens=False).ids)
    full = count_request_tokens(M, MSGS)
    assert full > bare


def test_mapping_missing_raises_no_char_fallback(monkeypatch):
    # model→tokenizer 映射缺失 → TokenizerUnavailable,绝不回退字符估算
    monkeypatch.setattr("nanmu_engine.token_count.TOKENIZER_MAP", {})
    with pytest.raises(TokenizerUnavailable):
        count_request_tokens("unknown-model", MSGS)


def test_deterministic():
    # 同输入两次计数一致,跨进程亦然
    assert count_request_tokens(M, MSGS) == count_request_tokens(M, MSGS)
