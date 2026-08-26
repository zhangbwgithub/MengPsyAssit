"""Qwen LLM provider（DashScope OpenAI 兼容端点）。

调用姿势对齐 tests/prompt_eval/run_prompt_eval.py（P0 实测通过）：
POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)

_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class QwenLLM(LLMProvider):
    """Qwen LLM provider（默认模型 qwen-max，由 Settings.llm_model 决定）。"""

    name = "qwen"

    def __init__(self, api_key: str, model: str = "qwen-max", *, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise ProviderError("dashscope_api_key 未配置，无法初始化 qwen provider")
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.Client(timeout=180.0)

    @staticmethod
    def build_messages(messages: list[dict], schema_hint: str | None) -> list[dict]:
        """组装最终 messages：schema_hint 非空时拼入 system 提示。"""
        if not schema_hint:
            return list(messages)
        hint_msg = {"role": "system", "content": f"请严格按以下结构要求输出：\n{schema_hint}"}
        if messages and messages[0].get("role") == "system":
            merged = dict(messages[0])
            merged["content"] = f"{merged.get('content', '')}\n\n{hint_msg['content']}"
            return [merged, *messages[1:]]
        return [hint_msg, *messages]

    def complete(
        self,
        messages: list[dict],
        *,
        schema_hint: str | None = None,
        temperature: float = 0.3,
    ) -> str:
        """对话补全，返回文本内容。"""
        body = {
            "model": self._model,
            "messages": self.build_messages(messages, schema_hint),
            "temperature": temperature,
        }
        payload = self._post_chat(body)
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"Qwen 响应结构异常: {payload}") from exc

    def health_check(self) -> bool:
        """探测策略：一次最小 completion（max_tokens≤5），真实验证 key + 模型可用。"""
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        }
        try:
            payload = self._post_chat(body)
        except ProviderError as exc:
            logger.warning("qwen health_check 失败: %s", exc)
            return False
        return bool(payload.get("choices"))

    def _post_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST chat/completions；异常与日志均不泄露 Authorization。"""
        try:
            resp = self._client.post(
                f"{_BASE_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                json=body,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(f"Qwen API 网络异常: {type(exc).__name__}: {exc}") from exc
        if resp.status_code >= 400:
            raise ProviderError(f"Qwen API HTTP {resp.status_code}: {resp.text}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(f"Qwen API 返回非 JSON: {resp.text[:200]}") from exc
