#!/usr/bin/env python3
"""T-0.1 测试音频合成流水线
3 类场景（正常对话 / 打断重叠 / 长停顿），双音色模拟 T(咨询师)+P(来访者)。
- 每句用 qwen3-tts-flash 单独合成（T=Ethan 男声, P=Cherry 女声）
- ffmpeg 按时间线拼接：普通场景 0.6s 间隔；打断场景负间隔(重叠)；长停顿场景插入 5-8s 静音
- 产出: tests/audio/*.wav (16kHz mono) + tests/golden/*.json (含 T/P 段落基准标注)
隐私红线：全部为合成内容，不含任何真实咨询数据。
"""
import json, os, subprocess, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PARTS = REPO / "tests/synth/_parts"
AUDIO_OUT = REPO / "tests/audio"
GOLDEN_OUT = REPO / "tests/golden"
TTS = Path.home() / ".hermes/profiles/qqbot/skills/qianwen/qianwen-audio-tts/scripts/tts.py"

VOICE = {"T": "Ethan", "P": "Cherry"}   # T=咨询师(男), P=来访者(女)
NORMAL_GAP = 0.6

def load_key():
    env = Path.home() / ".hermes/profiles/qqbot/.env"
    for line in env.read_text().splitlines():
        line = line.strip()
        if line.startswith("DASHSCOPE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("DASHSCOPE_API_KEY not found in qqbot .env")

KEY = load_key()

def synth(text, voice, out_path: Path):
    if out_path.exists() and out_path.stat().st_size > 1000:
        return  # 已合成过，复用
    out_path.parent.mkdir(parents=True, exist_ok=True)
    req = json.dumps({"text": text, "voice": voice}, ensure_ascii=False)
    r = subprocess.run(
        [sys.executable, str(TTS), "--request", req, "--output", str(out_path)],
        env=dict(os.environ, DASHSCOPE_API_KEY=KEY),
        capture_output=True, text=True, cwd=REPO, timeout=120)
    if r.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"TTS failed for {out_path.name}: rc={r.returncode}\n{r.stderr[-800:]}")

def dur(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(r.stdout.strip())

def compose(items, out_path: Path, sr=16000):
    """items: [(wav_path, start_sec), ...] 混音合成到 out_path"""
    total = max(s + dur(p) for p, s in items) + 0.3
    n = len(items)
    cmd = ["ffmpeg", "-y", "-v", "error"]
    filt = []
    for i, (p, s) in enumerate(items):
        cmd += ["-i", str(p)]
        ms = int(s * 1000)
        filt.append(f"[{i}:a]aresample={sr},aformat=sample_fmts=fltp:channel_layouts=mono,"
                    f"adelay={ms}:all=1[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(n))
    filt.append(f"{mix}amix=inputs={n}:normalize=0,alimiter=limit=0.95,"
                f"apad,atrim=0:{total:.3f},asetpts=N/SR/TB[out]")
    cmd += ["-filter_complex", ";".join(filt), "-map", "[out]",
            "-ac", "1", "-ar", str(sr), "-sample_fmt", "s16", str(out_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg mix failed: {r.stderr[-800:]}")

# ---------------- 场景剧本 ----------------
# turn: (speaker, text, gap_before)  gap_before=None 表示普通 0.6s 间隔；
# 负数 = 与上一句尾部重叠(打断)；正数>2 = 长停顿
SCENARIOS = {
    "01_normal_dialogue": {
        "desc": "正常对话：T/P 交替，常规间隔，含填充词",
        "turns": [
            ("T", "你好，请坐。这一周过得怎么样？", None),
            ("P", "嗯……就是，还是老样子，最近工作压力特别大，晚上经常睡不着。", None),
            ("T", "睡不着的时候，脑子里一般在想些什么呢？", None),
            ("P", "就是白天那些事嘛，然后会反复想，领导说的那句话到底是什么意思，然后越想越清醒。", None),
            ("T", "听起来，到了晚上，白天的那些事情会被反复地拿出来想。", None),
            ("P", "对，然后那个，其实我也知道想这些没什么用，但是就是停不下来。", None),
            ("T", "嗯，停不下来本身，可能比想的内容更让人累。", None),
            ("P", "嗯……对，就是那种感觉，白天已经很累了，晚上还要继续。", None),
        ],
    },
    "02_overlap_interruption": {
        "desc": "打断重叠：多处双说话人同时发声，压测说话人分离",
        "turns": [
            ("T", "那我们就从你上次提到的那件事开始聊吧。", None),
            ("P", "嗯，就是上周和我妈打电话那件事，其实我当时特别委屈，然后她就一直在讲道理。", None),
            ("T", "嗯。", -1.5),
            ("P", "她每讲一句道理，我就觉得更堵得慌。", -0.5),
            ("T", "她讲道理的时候，你的感受是……", -1.0),
            ("P", "就觉得很堵，不想再听了。", -0.8),
            ("T", "好，我们慢一点，一句一句来。", 0.8),
        ],
    },
    "03_long_pauses": {
        "desc": "长停顿：句中/句间含 5-8 秒静默，压测静音切分",
        "turns": [
            ("T", "上次我们聊到你和父亲的关系，这周有没有想起什么？", None),
            ("P", "嗯……", None),
            ("P", "想起来一件小事。就是我小学的时候，有一次下雨，他来给我送伞。", 6.0),
            ("T", "嗯，那次送伞。", None),
            ("P", "其实那时候……我不太想跟他说谢谢。", 8.0),
            ("T", "这句话里，好像有很多东西。愿意多说一点吗？", None),
            ("P", "就是……说不出口。", 5.0),
        ],
    },
}

def build(name, sc):
    print(f"== {name}: {sc['desc']} ==")
    items, turns_meta = [], []
    t = 0.0
    for i, (spk, text, gap) in enumerate(sc["turns"]):
        part = PARTS / name / f"{i:02d}_{spk}.wav"
        synth(text, VOICE[spk], part)
        d = dur(part)
        if i > 0:
            if gap is None:
                t += NORMAL_GAP
            else:
                t += gap  # 负数=重叠提前, 正数=长停顿
        t = max(t, 0.0)
        items.append((part, t))
        turns_meta.append({
            "idx": i, "speaker": spk, "role": "counselor" if spk == "T" else "client",
            "text": text, "start": round(t, 2), "end": round(t + d, 2),
        })
        t += d
        print(f"  [{i}] {spk} {d:5.2f}s @ {turns_meta[-1]['start']:6.2f}s  {text[:18]}…")
    out_wav = AUDIO_OUT / f"{name}.wav"
    compose(items, out_wav)
    golden = {
        "scenario": name,
        "description": sc["desc"],
        "audio": f"tests/audio/{name}.wav",
        "sample_rate": 16000, "channels": 1,
        "duration": round(dur(out_wav), 2),
        "voices": {"T": "Ethan (qwen3-tts-flash)", "P": "Cherry (qwen3-tts-flash)"},
        "note": "start/end 为拼接时间线的计划值（TTS 片段可能含极少量首尾静音，边界为约值）",
        "turns": turns_meta,
        "transcript": "\n".join(f"{m['speaker']}: {m['text']}" for m in turns_meta),
    }
    gpath = GOLDEN_OUT / f"{name}.json"
    gpath.write_text(json.dumps(golden, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  -> {out_wav} ({golden['duration']}s) + {gpath.name}\n")

if __name__ == "__main__":
    AUDIO_OUT.mkdir(parents=True, exist_ok=True)
    GOLDEN_OUT.mkdir(parents=True, exist_ok=True)
    for name, sc in SCENARIOS.items():
        build(name, sc)
    print("ALL DONE")
