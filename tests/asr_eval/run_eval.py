#!/usr/bin/env python3
"""ASR 选型评测脚本 CLI 入口。

用法示例：
    python3 run_eval.py --dry-run                    # 只打印执行计划
    python3 run_eval.py --model all                   # 评测全部候选
    python3 run_eval.py --model paraformer            # 只评测 paraformer-v2
    python3 run_eval.py --model qwen3-asr --audio tests/audio/01_normal_dialogue.wav
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 项目根目录
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS_DIR = _REPO_ROOT / "tests"
_AUDIO_DIR = _TESTS_DIR / "audio"
_GOLDEN_DIR = _TESTS_DIR / "golden"
_DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "results"

# 模型注册表
_MODELS = {
    "paraformer": {
        "name": "paraformer-v2",
        "provider": "paraformer",
        "needs_url": True,
        "supports_diarization": True,
        "supports_timestamps": True,
    },
    "qwen3-asr": {
        "name": "qwen3-asr-flash",
        "provider": "qwen_asr",
        "needs_url": False,
        "supports_diarization": False,
        "supports_timestamps": False,
    },
}


# ═══════════════════════════════════════════════════════════════
# 参数解析
# ═══════════════════════════════════════════════════════════════


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="ASR 选型评测脚本：比较 paraformer-v2 与 qwen3-asr-flash"
    )
    parser.add_argument(
        "--model",
        choices=["paraformer", "qwen3-asr", "all"],
        default="all",
        help="选择评测的模型 (默认: all)",
    )
    parser.add_argument(
        "--audio",
        action="append",
        default=[],
        help="音频文件路径（可多次指定，默认 tests/audio/ 下全部 .wav）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(_DEFAULT_OUT_DIR),
        help=f"结果输出目录 (默认: {_DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印执行计划，不发起网络请求",
    )
    return parser.parse_args()


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════


def resolve_audio_files(audio_args: list[str]) -> list[Path]:
    """解析音频文件列表。"""
    if audio_args:
        files = [Path(a).resolve() for a in audio_args]
        for f in files:
            if not f.is_file():
                print(f"错误：音频文件不存在: {f}", file=sys.stderr)
                sys.exit(1)
        return files
    # 默认：tests/audio/ 下全部 .wav
    return sorted(_AUDIO_DIR.glob("*.wav"))


def load_golden(audio_path: Path) -> dict | None:
    """加载对应的黄金基准 JSON。"""
    golden_path = _GOLDEN_DIR / (audio_path.stem + ".json")
    if golden_path.is_file():
        with open(golden_path, encoding="utf-8") as f:
            return json.load(f)
    return None


def compute_cer_from_golden(full_text: str, golden: dict) -> float | None:
    """计算 CER。ref 来自黄金 transcript。"""
    from cer import cer as calc_cer

    ref_text = golden.get("transcript", "")
    if not ref_text:
        return None
    # ref: 按 "T: xxx" 各行取文本拼接
    ref_lines: list[str] = []
    for line in ref_text.strip().splitlines():
        line = line.strip()
        if line.startswith("T: "):
            ref_lines.append(line[3:])
        elif line.startswith("P: "):
            ref_lines.append(line[3:])
        elif ": " in line:
            ref_lines.append(line.split(": ", 1)[1])
        else:
            ref_lines.append(line)
    ref_clean = "".join(ref_lines)
    return calc_cer(ref_clean, full_text)


def evaluate_speaker_diarization(
    sentences: list[dict], golden: dict
) -> dict[str, int | float | dict | None] | None:
    """说话人分离评估（仅 paraformer 适用）。

    策略：
    1. 把 ASR sentences 按时间中点匹配到黄金 turns
    2. 多数投票建立 speaker_id → 黄金标签 映射
    3. 计算一致率
    """
    if not sentences:
        return None

    golden_turns = golden.get("turns", [])
    if not golden_turns:
        return None

    # 第一步：匹配每个 ASR sentence 到最佳黄金 turn
    matches: list[dict] = []  # {"asr_speaker_id": int, "golden_speaker": str, "matched": bool}
    for sent in sentences:
        asr_mid = None
        begin_ms = sent.get("begin_ms")
        end_ms = sent.get("end_ms")
        if begin_ms is not None and end_ms is not None:
            asr_mid = (begin_ms + end_ms) / 2000.0  # 转为秒
        elif begin_ms is not None:
            asr_mid = begin_ms / 1000.0
        elif end_ms is not None:
            asr_mid = end_ms / 1000.0

        asr_sid = sent.get("speaker_id")
        if asr_sid is None:
            continue

        if asr_mid is None:
            # 无时间信息，跳过匹配
            matches.append(
                {"asr_speaker_id": asr_sid, "golden_speaker": None, "matched": False}
            )
            continue

        # 找时间交叠最大的黄金 turn
        best_turn = None
        best_overlap = -1.0
        for turn in golden_turns:
            t_start = turn.get("start", 0.0)
            t_end = turn.get("end", 0.0)
            # 计算重叠区间
            overlap_start = max(asr_mid - 1.0, t_start)  # ±1s 容差
            overlap_end = min(asr_mid + 1.0, t_end)
            overlap = overlap_end - overlap_start
            if overlap > best_overlap:
                best_overlap = overlap
                best_turn = turn

        if best_turn is not None and best_overlap > 0:
            matches.append(
                {
                    "asr_speaker_id": asr_sid,
                    "golden_speaker": best_turn.get("speaker"),
                    "matched": True,
                }
            )
        else:
            matches.append(
                {
                    "asr_speaker_id": asr_sid,
                    "golden_speaker": None,
                    "matched": False,
                }
            )

    if not matches:
        return None

    # 第二步：多数投票建立映射
    # 统计每个 asr_speaker_id 对应各黄金标签的出现次数
    vote_counts: dict[int, dict[str, int]] = {}
    for m in matches:
        sid = m["asr_speaker_id"]
        gs = m["golden_speaker"]
        if sid not in vote_counts:
            vote_counts[sid] = {}
        if gs is not None:
            vote_counts[sid][gs] = vote_counts[sid].get(gs, 0) + 1

    # 建立映射
    speaker_mapping: dict[int, str] = {}
    for sid, counts in vote_counts.items():
        if counts:
            speaker_mapping[sid] = max(counts, key=counts.get)

    # 第三步：计算一致率
    matched = 0
    mismatched = 0
    unknown = 0
    for m in matches:
        if m["golden_speaker"] is None:
            unknown += 1
            continue
        mapped = speaker_mapping.get(m["asr_speaker_id"])
        if mapped is None:
            unknown += 1
        elif mapped == m["golden_speaker"]:
            matched += 1
        else:
            mismatched += 1

    total_known = matched + mismatched
    accuracy = matched / total_known if total_known > 0 else None

    return {
        "speaker_mapping": {str(k): v for k, v in speaker_mapping.items()},
        "matched": matched,
        "mismatched": mismatched,
        "unknown": unknown,
        "accuracy": accuracy,
    }


# ═══════════════════════════════════════════════════════════════
# dry-run 模式
# ═══════════════════════════════════════════════════════════════


def print_dry_run_plan(
    models_to_eval: list[str], audio_files: list[Path], out_dir: Path
) -> None:
    """打印执行计划。"""
    print("=" * 60)
    print("ASR 选型评测 — 执行计划 (dry-run)")
    print("=" * 60)
    print()

    # 模型信息
    print("待评测模型：")
    total_requests = 0
    for mid in models_to_eval:
        minfo = _MODELS[mid]
        print(f"  • {mid} ({minfo['name']})")
        print(f"    - 需要公网URL: {'是' if minfo['needs_url'] else '否（支持本地文件）'}")
        print(
            f"    - 说话人分离: {'支持' if minfo['supports_diarization'] else '不支持（返回纯文本）'}"
        )
        print(f"    - 句级时间戳: {'支持' if minfo['supports_timestamps'] else '不支持'}")
    print()

    # 音频信息
    print("待评测音频：")
    for af in audio_files:
        size_kb = af.stat().st_size / 1024
        golden = load_golden(af)
        duration = golden.get("duration", "未知") if golden else "未知"
        print(f"  • {af.name} ({duration}s, {size_kb:.0f} KB)")
        if mid == "paraformer":
            print("    ⚠ paraformer-v2 需要公网可访问 URL，不支持本地文件路径")
    print()

    # 执行矩阵
    print("执行矩阵（模型 × 音频）：")
    for mid in models_to_eval:
        for af in audio_files:
            total_requests += 1
            marker = "⚠ 需URL" if _MODELS[mid]["needs_url"] else "✓ 可直接调用"
            print(f"  [{mid}] × [{af.name}] → {marker}")
    print()

    # 参数
    print("调用参数：")
    print("  • paraformer-v2: diarization_enabled=True, speaker_count=2, language_hints=['zh','en']")
    print("  • qwen3-asr-flash: result_format='message'")
    print()

    # 输出
    print(f"输出目录: {out_dir}")
    for mid in models_to_eval:
        print(f"  • {mid}_results.json")
    print()

    # 汇总
    print("汇总：")
    print(f"  • 总请求数: {total_requests}（每个请求仅 1 次 API 调用）")
    print("  • API Key 来源: 环境变量 DASHSCOPE_API_KEY")
    sdk_available = False
    try:
        import dashscope  # noqa: F401

        sdk_available = True
    except ImportError:
        pass
    print(f"  • dashscope SDK: {'已安装（将使用 SDK 路径）' if sdk_available else '未安装（将使用 HTTP 路径）'}")
    print()
    print("（dry-run 模式：未发起任何网络请求）")


# ═══════════════════════════════════════════════════════════════
# 实际评测
# ═══════════════════════════════════════════════════════════════


def run_paraformer(audio_path: Path) -> dict:
    """运行 paraformer-v2 评测。"""
    from providers.paraformer import transcribe

    # paraformer 需要 URL，这里我们传入本地路径作为占位
    # 执行时编排方会提供托管方案
    file_url = str(audio_path.resolve())
    return transcribe(file_url)


def run_qwen_asr(audio_path: Path) -> dict:
    """运行 qwen3-asr-flash 评测。"""
    from providers.qwen_asr import transcribe

    return transcribe(str(audio_path.resolve()))


def run_evaluation(
    models_to_eval: list[str], audio_files: list[Path], out_dir: Path
) -> None:
    """执行实际评测。"""
    out_dir.mkdir(parents=True, exist_ok=True)

    for mid in models_to_eval:
        minfo = _MODELS[mid]
        results: list[dict] = []

        print(f"\n{'='*60}")
        print(f"开始评测: {mid} ({minfo['name']})")
        print(f"{'='*60}")

        for audio_path in audio_files:
            print(f"\n  处理: {audio_path.name} ...")

            if mid == "paraformer":
                result = run_paraformer(audio_path)
            else:
                result = run_qwen_asr(audio_path)

            # 计算 CER
            golden = load_golden(audio_path)
            if golden and result.full_text:
                result.cer = compute_cer_from_golden(result.full_text, golden)

            # 说话人分离评估（仅 paraformer）
            if minfo["supports_diarization"] and result.sentences and golden:
                result.speaker_stats = evaluate_speaker_diarization(
                    result.sentences, golden
                )

            results.append(result.to_dict())

            status_icon = "✓" if result.status == "ok" else "✗"
            cer_str = f"CER={result.cer:.4f}" if result.cer is not None else "CER=N/A"
            latency_str = f"{result.latency_s:.2f}s" if result.latency_s else "N/A"
            print(f"    {status_icon} 状态={result.status}, 延迟={latency_str}, {cer_str}")

        # 写入结果文件
        result_file = out_dir / f"{mid}_results.json"
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n  结果已保存: {result_file}")


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════


def main() -> None:
    args = parse_args()

    # 解析模型
    if args.model == "all":
        models_to_eval = list(_MODELS.keys())
    else:
        models_to_eval = [args.model]

    # 解析音频
    audio_files = resolve_audio_files(args.audio)
    if not audio_files:
        print("错误：未找到任何音频文件", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir)

    if args.dry_run:
        print_dry_run_plan(models_to_eval, audio_files, out_dir)
        sys.exit(0)

    # 实际评测需要 API Key
    from providers import get_api_key

    get_api_key()  # 缺失时会 sys.exit(2)

    run_evaluation(models_to_eval, audio_files, out_dir)


if __name__ == "__main__":
    # 将脚本所在目录加入 sys.path，确保 from cer / from providers 正确解析
    _script_dir = str(Path(__file__).resolve().parent)
    if _script_dir not in sys.path:
        sys.path.insert(0, _script_dir)
    main()
