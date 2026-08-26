"""Prompt 模板加载与占位符替换。

- 模板目录可配置（默认 app/backend/prompts，相对仓库根解析）
- 版本化模板：clean/v1.md、record/v1.md
- 替换占位符用简单字符串替换（任务卡路线决策 7）
"""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .response import ApiError

_TEMPLATES = {
    "clean": ("clean", "v1", "{{transcript}}"),
    "record": ("record", "v1", "{{cleaned_transcript}}"),
}


def _repo_root() -> Path:
    """仓库根：本项目包位于 <root>/app/backend/src/psyapp。"""
    return Path(__file__).resolve().parents[4]


def _prompts_dir(settings: Settings | None = None) -> Path:
    if settings is not None and settings.prompts_dir:
        return Path(settings.prompts_dir)
    return _repo_root() / "app" / "backend" / "prompts"


def load_prompt(name: str, settings: Settings | None = None) -> str:
    """读取模板文本；缺失抛 500。"""
    if name not in _TEMPLATES:
        raise ApiError("prompt_missing", f"未知 prompt: {name}", http_status=500)
    rel_dir, version, _ = _TEMPLATES[name]
    path = _prompts_dir(settings) / rel_dir / f"{version}.md"
    if not path.is_file():
        raise ApiError(
            "prompt_missing", f"Prompt 模板缺失: {path}", http_status=500
        )
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, *, settings: Settings | None = None, **kwargs: str) -> str:
    """读取模板并替换占位符；缺少占位符值抛 500。"""
    _, _, placeholder = _TEMPLATES[name]
    template = load_prompt(name, settings)
    for key, value in kwargs.items():
        marker = "{{" + key + "}}"
        if marker not in template:
            raise ApiError(
                "prompt_render", f"模板缺少占位符 {marker}", http_status=500
            )
        template = template.replace(marker, value)
    if placeholder in template:
        raise ApiError(
            "prompt_render", f"占位符 {placeholder} 未被替换", http_status=500
        )
    return template
