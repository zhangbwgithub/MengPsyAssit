# ASR 选型评测脚本

## 概述

本目录包含 ASR（自动语音识别）选型评测脚本，用于比较两个 DashScope ASR 候选模型：
- **paraformer-v2**：录音文件识别，异步任务，支持说话人分离
- **qwen3-asr-flash**：同步多模态 chat 风格，返回纯文本

评测指标：字错率（CER）、说话人分离准确率（仅 paraformer）、API 延迟。

## 目录结构

```
tests/asr_eval/
├── run_eval.py          # CLI 入口
├── cer.py               # 纯标准库 CER 计算（字符级 Levenshtein）
├── providers/
│   ├── __init__.py      # 统一结果格式与工具函数
│   ├── paraformer.py    # 候选 1：paraformer-v2
│   └── qwen_asr.py      # 候选 2：qwen3-asr-flash
└── README.md            # 本文件
```

## 快速开始

### 1. 设置 API Key

```bash
export DASHSCOPE_API_KEY='sk-...'
```

### 2. 运行评测

```bash
# 评测全部候选（默认）
python3 tests/asr_eval/run_eval.py

# 只评测某个模型
python3 tests/asr_eval/run_eval.py --model paraformer
python3 tests/asr_eval/run_eval.py --model qwen3-asr

# 指定音频文件
python3 tests/asr_eval/run_eval.py --audio tests/audio/01_normal_dialogue.wav

# 自定义输出目录
python3 tests/asr_eval/run_eval.py --out-dir results/my_eval

# 试运行（不实际调用 API）
python3 tests/asr_eval/run_eval.py --dry-run
```

### 3. 查看结果

结果保存在 `tests/asr_eval/results/`（默认）：
- `paraformer_results.json`
- `qwen3-asr_results.json`

每条记录包含：
```json
{
  "model": "paraformer-v2",
  "audio": "tests/audio/01_normal_dialogue.wav",
  "status": "ok",
  "latency_s": 12.34,
  "full_text": "你好请坐这一周过得怎么样...",
  "sentences": [
    {
      "text": "你好请坐。",
      "begin_ms": 0,
      "end_ms": 2480,
      "speaker_id": 0
    }
  ],
  "cer": 0.0523,
  "speaker_stats": {
    "speaker_mapping": {"0": "T", "1": "P"},
    "matched": 8,
    "mismatched": 1,
    "unknown": 0,
    "accuracy": 0.889
  },
  "error": null
}
```

## 候选模型能力差异

| 特性 | paraformer-v2 | qwen3-asr-flash |
|------|---------------|-----------------|
| 调用方式 | 异步任务（提交→轮询→获取结果） | 同步调用（直接返回） |
| 输入格式 | 公网可访问 URL（不支持本地文件） | 本地文件绝对路径 / URL / base64 |
| 说话人分离 | ✅ 支持（speaker_id） | ❌ 不支持 |
| 句级时间戳 | ✅ 支持（begin_time/end_time，毫秒） | ❌ 不支持 |
| 返回格式 | 结构化 JSON（每句独立） | 纯文本 |
| 语言提示 | 支持（language_hints 参数） | 不支持 |
| 限流策略 | 未知（需测试） | 100 RPM |
| 适用场景 | 需要时间戳和说话人分离的场景 | 快速转写，无需细粒度信息 |

## 依赖

### 必需
- Python 3.11+（系统自带）

### 可选（增强）
- `dashscope` SDK：提供更简洁的 API 封装

**安装 dashscope SDK（可选）：**

```bash
# 使用 uv（推荐）
uv pip install dashscope

# 或在项目 .venv 中安装
python3 -m venv .venv
source .venv/bin/activate
pip install dashscope
```

**注意：** 脚本会自动检测 `dashscope` SDK 是否可用：
- 若已安装，优先使用 SDK 路径
- 若未安装，自动回退到纯标准库 `urllib.request` 实现

## 评测逻辑

### CER（字错率）

- 使用字符级 Levenshtein 编辑距离
- 归一化：去除所有中英文标点符号和空白
- 公式：`CER = edit_distance(ref, hyp) / max(len(ref), 1)`
- 黄金标准来自 `tests/golden/*.json` 的 `transcript` 字段

### 说话人分离评估（仅 paraformer）

1. **时间匹配**：将 ASR sentences 按时间中点匹配到黄金 turns（容差 ±1s）
2. **多数投票**：统计每个 ASR speaker_id 对应各黄金标签的出现次数，建立映射
3. **一致率计算**：
   - `matched`：映射后标签一致的句子数
   - `mismatched`：映射后标签不一致的句子数
   - `unknown`：无法匹配到黄金 turn 的句子数
   - `accuracy = matched / (matched + mismatched)`

### 延迟测量

- 测量从 API 请求开始到响应结束的完整时间
- paraformer-v2：包含提交 + 轮询 + 结果下载的总时间
- qwen3-asr-flash：单次请求的往返时间

## 注意事项

1. **paraformer-v2 需要公网 URL**：脚本接受本地路径，但实际执行时需要编排方提供音频托管方案
2. **黄金基准的 start/end 是约值**：有 ±0.5s 左右的误差，用于说话人匹配时会容差处理
3. **qwen3-asr-flash 无时间戳和说话人信息**：CER 只能基于全文计算，说话人分离评估为 N/A
4. **脚本不会自动安装依赖**：需要手动安装 `dashscope` SDK（若需要）
5. **API Key 安全**：从环境变量读取，绝不硬编码；缺失时退出码 2

## 自检

```bash
# 运行 cer.py 自检（纯标准库，无需网络）
python3 tests/asr_eval/cer.py

# 检查所有 .py 文件语法
python3 -m py_compile tests/asr_eval/cer.py
python3 -m py_compile tests/asr_eval/run_eval.py
python3 -m py_compile tests/asr_eval/providers/__init__.py
python3 -m py_compile tests/asr_eval/providers/paraformer.py
python3 -m py_compile tests/asr_eval/providers/qwen_asr.py

# dry-run 模式（验证 CLI 参数解析）
python3 tests/asr_eval/run_eval.py --dry-run
```
