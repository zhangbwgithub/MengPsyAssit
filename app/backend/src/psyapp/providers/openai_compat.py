"""OpenAI 兼容端点 LLM provider 基类（MIMO / DeepSeek 共用）。

端点均为 POST {base_url}/chat/completions，Bearer 鉴权，
返回结构 choices[0].message.content（同 OpenAI）。纯 httpx，不引 SDK。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)


class OpenAICompatLLM(LLMProvider):
    """OpenAI 兼容 chat/completions 端点的通用实现。

    子类只需定义 name / _BASE_URL / _DEFAULT_MODEL / _KEY_ENV_NAME。
    """

    name = "openai-compat"
    _BASE_URL: str = ""
    _DEFAULT_MODEL: str = ""
    _KEY_ENV_NAME: str = ""  # 缺 key 时提示的环境变量名（不打印 key 本体）

    def __init__(
        self,
        api_key: str,
        model: str = "",
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ProviderError(
                f"{self._KEY_ENV_NAME} 未配置，无法初始化 {self.name} provider"
            )
        self._api_key = api_key
        self._model = model or self._DEFAULT_MODEL
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
            raise ProviderError(f"{self.name} 响应结构异常: {payload}") from exc

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
            logger.warning("%s health_check 失败: %s", self.name, exc)
            return False
        return bool(payload.get("choices"))

    def _post_chat(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST chat/completions；异常与日志均不泄露 Authorization。"""
        try:
            resp = self._client.post(
                f"{self._BASE_URL}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                json=body,
            )
        except httpx.HTTPError as exc:
            raise ProviderError(
                f"{self.name} API 网络异常: {type(exc).__name__}: {exc}"
            ) from exc
        if resp.status_code >= 400:
            raise ProviderError(f"{self.name} API HTTP {resp.status_code}: {resp.text}")
        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError(f"{self.name} API 返回非 JSON: {resp.text[:200]}") from exc
