"""音频上传校验与落盘（随机文件名，防枚举）。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from .response import ApiError

# S0 只收这 5 种；大小上限 200MB（任务卡路线决策 5/6）
ALLOWED_EXTENSIONS = {".wav", ".m4a", ".mp3", ".opus", ".flac"}
MAX_AUDIO_BYTES = 200 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024


def validate_audio_ext(filename: str | None) -> str:
    """校验扩展名，返回小写扩展名；非法抛 ApiError(422)。"""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ext for ext in ALLOWED_EXTENSIONS))
        raise ApiError(
            "invalid_file_type",
            f"不支持的音频格式 {suffix or '(无扩展名)'}，仅支持 {allowed}",
            http_status=422,
        )
    return suffix


async def save_upload_to_audio_dir(file: UploadFile, audio_dir: Path, suffix: str) -> str:
    """把上传文件流式写入 audio_dir，文件名为 uuid4 随机名（不保留原名）。

    写入途中统计字节数，超过 200MB 上限即中断并清理残片，抛 ApiError(413)；
    其余写入失败抛 ApiError(500)。返回落盘路径字符串。
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{suffix}"
    dest = audio_dir / filename
    try:
        total = 0
        with dest.open("wb") as out:
            while chunk := await file.read(_CHUNK_BYTES):
                total += len(chunk)
                if total > MAX_AUDIO_BYTES:
                    raise ApiError(
                        "file_too_large",
                        f"音频文件超过 {MAX_AUDIO_BYTES // (1024 * 1024)}MB 上限",
                        http_status=413,
                    )
                out.write(chunk)
    except ApiError:
        dest.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise ApiError("audio_save_failed", "音频文件保存失败", http_status=500) from exc
    return str(dest)
