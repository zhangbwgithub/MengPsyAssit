"""DeepSeek LLM provider（OpenAI 兼容端点）。

端点：POST https://api.deepseek.com/v1/chat/completions
鉴权 Bearer DEEPSEEK_API_KEY；默认模型 deepseek-v4-flash。
注意：该模型带 reasoning，输出较慢（59 段 clean 实测约 2 分钟），超时已给足 180s。
"""

from __future__ import annotations

from .openai_compat import OpenAICompatLLM


class DeepseekLLM(OpenAICompatLLM):
    """DeepSeek LLM provider（默认模型 deepseek-v4-flash，由 Settings.llm_model 决定）。"""

    name = "deepseek"
    _BASE_URL = "https://api.deepseek.com/v1"
    _DEFAULT_MODEL = "deepseek-v4-flash"
    _KEY_ENV_NAME = "DEEPSEEK_API_KEY"
