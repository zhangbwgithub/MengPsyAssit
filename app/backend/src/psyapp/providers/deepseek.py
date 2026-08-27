"""DeepSeek LLM provider（OpenAI 兼容端点）。

端点：POST https://api.deepseek.com/v1/chat/completions
鉴权 Bearer DEEPSEEK_API_KEY；默认模型 deepseek-v4-flash。
T-S1.5：deepseek-v4-flash 是推理模型，默认带 thinking 时输出大量推理 tokens；
OpenAI 兼容端点传 `"thinking": {"type": "disabled"}` 关闭思考，且该模式下 DeepSeek API
硬性要求 temperature = 0.2（否则报错）。因此本 provider 的 complete 固定这两个参数，
不受调用方 temperature 影响；health_check 仍走 max_tokens=5 最小探测，不改。
"""

from __future__ import annotations

from .openai_compat import OpenAICompatLLM


class DeepseekLLM(OpenAICompatLLM):
    """DeepSeek LLM provider（默认模型 deepseek-v4-flash，由 Settings.llm_model 决定）。"""

    name = "deepseek"
    _BASE_URL = "https://api.deepseek.com/v1"
    _DEFAULT_MODEL = "deepseek-v4-flash"
    _KEY_ENV_NAME = "DEEPSEEK_API_KEY"

    def complete(
        self,
        messages: list[dict],
        *,
        schema_hint: str | None = None,
        temperature: float = 0.3,
    ) -> str:
        """关闭 thinking 的补全；temperature 固定 0.2（DeepSeek API 硬约束）。"""
        return super().complete(
            messages,
            schema_hint=schema_hint,
            temperature=0.2,
            extra_body={"thinking": {"type": "disabled"}},
        )
