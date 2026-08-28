"""Qwen3.5-Omni-Plus 多模态直转 provider（T-S1.6）。

复用 OpenAICompatLLM 的 HTTP 层（同 OpenAI 兼容端点、Bearer 鉴权、响应解析），
但请求/响应结构不同：messages 为音频多模态数组，返回的是转写+清理后的轮次文本。
本 provider 不进入 get_llm_provider 工厂——它不是文本 LLM，不参与 clean/record。
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

import httpx

from ..enums import Role
from .base import ProviderError
from .openai_compat import OpenAICompatLLM

logger = logging.getLogger(__name__)

OMNI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
OMNI_MODEL = "qwen3.5-omni-plus"
OMNI_KEY_ENV_NAME = "DASHSCOPE_API_KEY"

# 转写+清洗 prompt v2（FB-009 陛下拍板升级，称呼语铁证锚定修复角色翻转；照抄勿改写）
OMNI_TRANSCRIBE_PROMPT = """请完整转写这段心理咨询录音，并直接输出清理后的对话稿。要求：
1. 先听完全篇判断说话人角色（咨询师/来访者），在每一轮标注角色。角色判定铁律：
   a) 称呼语优先：若一方称呼另一方为「某某老师」，说话人一定不是该老师本人，对方才是；
   b) 不要假设「提问者=咨询师」：存在来访者强势追问、咨询师被动防御的对话，角色判定以称呼语和自述内容为准；
   c) 全篇一致性：同一人的声音在全篇中角色标注必须一致，若发现中途翻转，重新核对全篇。
2. 按对话轮次组织输出：同一人连续说的话合并为一轮；纯语气词（嗯/啊/对）不单独成轮，并入相邻轮次或删除。
3. 清理口语：去除填充词，合并被拆散的句子，修正明显的语音识别错误和指代（根据上下文判断他/她），修正重复字（如「是是」→「是」）。
4. 保留原意和说话风格，不添加、不总结；笑声、叹气等非语言信息用（笑）等形式保留。
5. 输出格式（每轮一行）：轮次号	角色	内容"""

_OMNI_AUDIO_FORMATS = {
    ".mp3": "mp3",
    ".wav": "wav",
    ".m4a": "m4a",
    ".opus": "opus",
    ".flac": "flac",
}


class QwenOmniLLM(OpenAICompatLLM):
    """qwen3.5-omni-plus 多模态音频直转（转写+清理+角色判定一步到位）。"""

    name = OMNI_MODEL
    _BASE_URL = OMNI_BASE_URL
    _DEFAULT_MODEL = OMNI_MODEL
    _KEY_ENV_NAME = OMNI_KEY_ENV_NAME

    def __init__(
        self,
        api_key: str,
        model: str = "",
        *,
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(
            api_key,
            model or OMNI_MODEL,
            client=client or httpx.Client(timeout=300.0),
        )

    def transcribe_audio(self, audio_path: str, prompt: str) -> str:
        """读本地音频 → base64 → 组多模态请求 → 返回 choices[0].message.content 文本。

        请求体照大统领先导探针结构：content 数组 [input_audio, text]、
        顶层 modalities=["text"]、enable_thinking=false、非流式。
        """
        path = Path(audio_path)
        if not path.is_file():
            raise ProviderError(f"音频文件不存在: {path}")
        audio_bytes = path.read_bytes()
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        audio_format = _OMNI_AUDIO_FORMATS.get(path.suffix.lower(), "mp3")

        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:;base64,{audio_b64}",
                                "format": audio_format,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            "modalities": ["text"],
            "enable_thinking": False,
        }
        payload = self._post_chat(body)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name} 响应结构异常: {payload}") from exc
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(parts)
        if not isinstance(content, str):
            raise ProviderError(f"{self.name} 响应 content 非文本: {content!r}")
        return content


# ── omni 轮次文本解析 ────────────────────────────────────────────────


def _split_role_content(seq: int, role_and_content: str) -> tuple[int, str, str] | None:
    """把「来访者：内容」这类没有空白分隔的角色+内容按首个冒号切开。"""
    for sep in ("：", ":"):
        if sep in role_and_content:
            role, content = role_and_content.split(sep, 1)
            if role.strip() and content.strip():
                return seq, role.strip(), content.strip()
    return None


def _split_omni_line(line: str) -> tuple[int, str, str] | None:
    """把一行拆成 (轮次号, 角色, 内容)。

    优先按 \\t 切三字段；切不开则按空白切「序号 角色 内容」，容忍空格分隔写法；
    再切不开则按「序号 角色：内容」首个冒号容错（「来访者：」带冒号写法）。
    """
    if "\t" in line:
        parts = line.split("\t")
        parts = [p.strip() for p in parts]
        if len(parts) >= 3 and parts[0].isdigit() and parts[1]:
            return int(parts[0]), parts[1], "\t".join(parts[2:]).strip()
        if len(parts) == 2 and parts[0].isdigit():
            return _split_role_content(int(parts[0]), parts[1])
        return None

    parts = line.split(None, 2)
    if len(parts) >= 3 and parts[0].isdigit():
        return int(parts[0]), parts[1], parts[2].strip()
    if len(parts) == 2 and parts[0].isdigit():
        return _split_role_content(int(parts[0]), parts[1])
    return None


def _normalize_role_text(raw: str) -> str:
    """去掉「来访者：」这类冒号写法，返回角色原词。"""
    return raw.strip().rstrip("：:").strip()


def parse_omni_transcript(text: str) -> list[dict[str, Any]]:
    """逐行解析 omni 直转输出，返回可直接落库的 segment dict 列表。

    - 空行跳过；无法解析的行跳过（模型可能输出围栏/前言）。
    - 角色映射：咨询师→T、来访者→P；其他角色文本归 P 兜底并保留原词为 role_label。
    - speaker 代号按角色标签首现序分配 A/B/C…（沿用现有 assign_speaker_codes 规则）。
    - seq 从 0 重排；content=cleaned_content=该行内容；start_ms/end_ms=None。
    """
    segments: list[dict[str, Any]] = []
    code_by_label: dict[str, str] = {}
    next_code = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parsed = _split_omni_line(line)
        if parsed is None:
            continue
        _seq, role_text, content = parsed
        content = content.strip()
        if not content:
            continue
        role_label = _normalize_role_text(role_text)
        if not role_label:
            continue

        role = Role.THERAPIST if role_label == "咨询师" else Role.PATIENT
        if role_label not in code_by_label:
            code_by_label[role_label] = chr(ord("A") + next_code)
            next_code += 1

        segments.append(
            {
                "seq": len(segments),
                "speaker": code_by_label[role_label],
                "role": role,
                "role_label": role_label,
                "content": content,
                "cleaned_content": content,
                "start_ms": None,
                "end_ms": None,
                "confidence": None,
            }
        )
    return segments
