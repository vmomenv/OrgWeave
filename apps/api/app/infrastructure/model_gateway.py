"""LiteLLM model gateway client (OpenAI-compatible)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import OrgWeaveSettings

logger = logging.getLogger("orgweave.model_gateway")


class ModelGatewayError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


async def chat_completion(
    settings: OrgWeaveSettings,
    *,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    """Call LiteLLM and return the first assistant message plus usage.

    The API key never appears in prompts or logs. Errors are surfaced without
    echoing request headers.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": max_tokens,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"content-type": "application/json"}
    if settings.litellm_master_key:
        headers["authorization"] = f"Bearer {settings.litellm_master_key}"

    try:
        async with httpx.AsyncClient(
            base_url=settings.litellm_base_url.rstrip("/"),
            timeout=timeout_seconds,
        ) as client:
            response = await client.post("/v1/chat/completions", json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise ModelGatewayError(f"模型网关不可用：{exc.__class__.__name__}") from exc

    if response.status_code != 200:
        detail = ""
        try:
            body = response.json()
            detail = str(body.get("error", {}).get("message", ""))[:300]
        except ValueError:
            detail = response.text[:300]
        raise ModelGatewayError(
            f"模型调用失败（HTTP {response.status_code}）{(': ' + detail) if detail else ''}",
            status_code=response.status_code,
        )

    try:
        body = response.json()
        choice = body["choices"][0]
        message = choice["message"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelGatewayError("模型响应格式无效") from exc

    usage = body.get("usage") or {}
    return {
        "message": {
            "role": "assistant",
            "content": message.get("content"),
            "tool_calls": message.get("tool_calls") or [],
        },
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }
