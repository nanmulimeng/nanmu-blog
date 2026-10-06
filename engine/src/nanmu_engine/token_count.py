"""Tokenizer 计数模块(离线、确定性、零网络)。

资源依据(Task 1 Step 1 核对,2026-10-06):
- API 模型 deepseek-flash = DeepSeek V4 系列(budget.md 价目快照 Flash 档);
- 官方离线资源:HF deepseek-ai/DeepSeek-V4-Flash 仓库 tokenizer.json(MIT,
  非 gated),锁定于 engine/resources/tokenizers/deepseek-v4-flash/,
  git blob = 628e3364caad11bdf9e67cea06eae7878122811d(内容寻址,与官方
  发布渠道 blobId 一致,镜像下载经哈希校验);
- 完整消息计数方式:按仓库官方 encoding/encoding_dsv4.py
  (encode_messages, thinking_mode="chat", add_default_bos_token=True)
  语义渲染 messages 为完整 prompt(BOS + system + <｜User｜> + user +
  <｜Assistant｜> + </think>,结构开销计入)后编码计数;
- 初始校准系数 = 1.0(依据=资源即服务端分词器,units/model-calls.md
  §3 规则 11);样本对账走 Task 22/26 校准通道。

计数不可得(映射缺失/资源加载失败/不支持的 role)→ 抛 TokenizerUnavailable,
无任何字符比例回退(规则 2:计数不可得→不出网)。
"""

from __future__ import annotations

from pathlib import Path

from tokenizers import Tokenizer

_ENGINE_ROOT = Path(__file__).resolve().parents[2]
_RESOURCE_DIR = _ENGINE_ROOT / "resources" / "tokenizers"


class TokenizerUnavailable(Exception):
    """token 计数不可得(映射缺失/资源加载失败/消息形态不支持)。"""


# model → 资源映射(Task 2 起由 config 提供并接管;version = tokenizer.json
# 的 git blob 哈希,内容寻址,与 HF 发布渠道 blobId 同构可验)。
TOKENIZER_MAP: dict[str, dict[str, str]] = {
    "deepseek-flash": {
        "resource": "deepseek-ai/DeepSeek-V4-Flash",
        "path": "deepseek-v4-flash/tokenizer.json",
        "version": "628e3364caad11bdf9e67cea06eae7878122811d",
    },
}

# V4 官方消息模板特殊 token(encoding/encoding_dsv4.py)
_BOS = "<｜begin▁of▁sentence｜>"
_USER = "<｜User｜>"
_ASSISTANT = "<｜Assistant｜>"
_THINK_END = "</think>"  # chat 模式:<｜Assistant｜> 后立即闭合 think 块

_tokenizer_cache: dict[str, Tokenizer] = {}


def load_tokenizer(model: str) -> Tokenizer:
    """加载 model 对应的锁定版 tokenizer;映射缺失或加载失败即
    TokenizerUnavailable,无字符比例回退。"""
    entry = TOKENIZER_MAP.get(model)
    if entry is None:
        raise TokenizerUnavailable(
            f"模型 {model!r} 无 tokenizer 映射(不回退字符估算,不出网)"
        )
    if model not in _tokenizer_cache:
        path = _RESOURCE_DIR / entry["path"]
        try:
            _tokenizer_cache[model] = Tokenizer.from_file(str(path))
        except Exception as exc:  # 资源缺失/损坏/格式不识别都归为不可得
            raise TokenizerUnavailable(
                f"tokenizer 资源加载失败:{model!r} <- {path}({exc})"
            ) from exc
    return _tokenizer_cache[model]


def _render_prompt(messages: list[dict]) -> str:
    """按官方 encoding_dsv4.py(thinking_mode="chat")语义渲染完整 prompt。

    支持的消息形态 = M1 实际发送形态:system 前置 + user 序列。
    其他 role(如 assistant 历史)→ TokenizerUnavailable(宁拒计数不出网,
    不猜测模板)。
    """
    parts = [_BOS]
    n = len(messages)
    for i, msg in enumerate(messages):
        role = msg.get("role")
        content = msg.get("content") or ""
        if role == "system":
            parts.append(content)
        elif role == "user":
            parts.append(_USER + content)
        else:
            raise TokenizerUnavailable(
                f"消息计数方式不支持 role={role!r}(拒计数=不出网)"
            )
        if i + 1 == n and role == "user":
            parts.append(_ASSISTANT + _THINK_END)
    return "".join(parts)


def count_request_tokens(model: str, messages: list[dict]) -> int:
    """对完整请求消息数组(含 role/结构开销与全部 content)确定性计数。

    add_special_tokens=False:特殊标记已按官方模板显式渲染,避免
    post-processor 再插入模板 token 造成双计;added_tokens 中的标记仍会被
    识别为单 token 计入。
    """
    tokenizer = load_tokenizer(model)
    prompt = _render_prompt(messages)
    return len(tokenizer.encode(prompt, add_special_tokens=False).ids)
