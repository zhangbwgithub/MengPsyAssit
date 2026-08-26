"""MIMO LLM provider（小米 MIMO，OpenAI 兼容端点）。

端点（T-S0.6 实测连通）：
POST https://token-plan-cn.xiaomimimo.com/v1/chat/completions
鉴权 Bearer XIAOMI_CN_API_KEY；默认模型 mimo-v2.5-pro（T-S0.6 起为全项目默认 LLM）。
"""

from __future__ import annotations

from .openai_compat import OpenAICompatLLM


class MimoLLM(OpenAICompatLLM):
    """MIMO LLM provider（默认模型 mimo-v2.5-pro，由 Settings.llm_model 决定）。"""

    name = "mimo"
    _BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
    _DEFAULT_MODEL = "mimo-v2.5-pro"
    _KEY_ENV_NAME = "XIAOMI_CN_API_KEY"
