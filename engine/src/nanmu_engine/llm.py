"""LLM HTTP 客户端(DeepSeek /chat/completions,非流式,单次调用单次返回)。

调用契约 = design.md"llm.py 调用契约"(2026-10-04 官方文档复核):
- 顶层显式 thinking=disabled / response_format=json_object / max_tokens /
  stream=false,无 extra_body 层(那是 OpenAI SDK 封装,本项目未引入);
- key 只从环境变量读,不进 config/log;
- 禁用透明重试(重试判定在 ledger/业务层,客户端不自行重发);
- 传输异常(超时/连接断)向上抛 httpx 原生异常,由 classify_failure 归
  E3.unknown;HTTP 有响应(含 4xx/5xx)返回 LLMResult,不在此判定业务。

错误分类矩阵 = design.md"错误分类与退出码":
no_retry={E1.request(400/401/422 及未列出状态), E4.terminal(非 stop
finish_reason,含 length), E5.balance(402)};
retryable={E3.http(429/500/503), E4.parse(200+stop 但 content 空/非合法 JSON)};
unknown={E3.unknown(超时/连接错误)}。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx

DEFAULT_BASE_URL = "https://api.deepseek.com"
API_KEY_ENV = "DEEPSEEK_API_KEY"
_MESSAGE_TRUNCATE = 200


@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: list[dict]
    max_tokens: int
    purpose: str            # score/understand/summarize/calibration
    request_hash: str


@dataclass(frozen=True)
class LLMResult:
    http_status: int | None
    finish_reason: str | None
    content: str | None
    json_parsed: bool
    usage: dict | None
    provider_request_id: str | None
    error_message: str | None


def call_llm(request: LLMRequest, *, transport: httpx.BaseTransport | None = None,
             base_url: str | None = None, timeout: float = 60.0) -> LLMResult:
    """单次 POST /chat/completions,单次返回;失败也返回 LLMResult,传输层
    异常(httpx 超时/连接类)按原样抛出(归 E3.unknown)。"""
    api_key = os.environ.get(API_KEY_ENV, "")
    url = (base_url or DEFAULT_BASE_URL).rstrip("/") + "/chat/completions"
    body = {
        "model": request.model,
        "messages": request.messages,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": request.max_tokens,
        "stream": False,
    }
    with httpx.Client(transport=transport, timeout=timeout) as client:
        response = client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        )
    return _parse_response(response)


def _parse_response(response: httpx.Response) -> LLMResult:
    payload: dict | None = None
    error_message: str | None = None
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        payload = None
        error_message = f"HTTP {response.status_code}:响应非 JSON"

    finish_reason = None
    content = None
    usage = None
    request_id = None
    if isinstance(payload, dict):
        request_id = payload.get("id")
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        choices = payload.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            choice = choices[0]
            finish_reason = choice.get("finish_reason")
            message = choice.get("message")
            if isinstance(message, dict):
                content = message.get("content")
        if error_message is None and response.status_code >= 400:
            err = payload.get("error")
            if isinstance(err, dict):
                error_message = str(err.get("message", "")) or None

    json_parsed = False
    if response.status_code == 200 and isinstance(content, str) and content:
        try:
            json.loads(content)
            json_parsed = True
        except (json.JSONDecodeError, ValueError):
            json_parsed = False

    return LLMResult(
        http_status=response.status_code,
        finish_reason=finish_reason,
        content=content,
        json_parsed=json_parsed,
        usage=usage,
        provider_request_id=request_id,
        error_message=error_message,
    )


def classify_failure(result_or_exc) -> tuple[str | None, dict]:
    """按矩阵返回 (error_class, fail_detail)。

    正常结果(200+stop+合法 JSON)返回 (None, {})——不是失败,不产生
    错误类别;调用方只在失败/unknown 时调用本函数。
    fail_detail = {http_status:int?, matrix_code:str, message:截断摘要}。
    """
    if isinstance(result_or_exc, BaseException):
        return "unknown", _detail(
            None, "E3.unknown",
            f"{type(result_or_exc).__name__}: {result_or_exc}")

    result: LLMResult = result_or_exc
    status = result.http_status

    if status is None:
        return "unknown", _detail(None, "E3.unknown",
                                  result.error_message or "无 HTTP 状态")
    if status == 402:
        return "no_retry", _detail(status, "E5.balance", result.error_message)
    if status in (400, 401, 422):
        return "no_retry", _detail(status, "E1.request", result.error_message)
    if status in (429, 500, 503):
        return "retryable", _detail(status, "E3.http", result.error_message)
    if status != 200:
        # 未列出的 HTTP 状态:保留响应,按不可自动重试的 E1.request 处理
        return "no_retry", _detail(status, "E1.request", result.error_message)

    # HTTP 200:非正常终止优先于解析判定(截断输出即使 JSON 恰好可解析也不可消费)
    if result.finish_reason != "stop":
        return "no_retry", _detail(
            status, "E4.terminal",
            result.error_message or f"finish_reason={result.finish_reason!r}")
    if not result.json_parsed:
        return "retryable", _detail(
            status, "E4.parse",
            result.error_message or "content 为空或非合法 JSON")
    return None, {}


def _detail(status: int | None, code: str, message: str | None) -> dict:
    text = (message or "")[:_MESSAGE_TRUNCATE]
    return {"http_status": status, "matrix_code": code, "message": text}
