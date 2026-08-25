# P0 技术验证报告（草稿）

> 日期：2026-08-25 · 大统领编制 · 状态：**定稿，三项任务全部完成**，待陛下拍板选型
> 目标（任务书）：为选型提供真实数据，钉死技术路线后进 S0 走骨架。

## 1. T-0.1 测试音频合成 ✅

- 3 场景双音色合成音频（qwen3-tts-flash，T=Ethan 男声/P=Cherry 女声）：
  - `01_normal_dialogue.wav` 43.4s — 正常对话，含填充词
  - `02_overlap_interruption.wav` 18.7s — 打断重叠（负间隔拼接），压测说话人分离
  - `03_long_pauses.wav` 41.6s — 5-8 秒长停顿，压测静音切分
- 黄金文字稿 3 份（逐句 speaker/text/计划时间戳），入库作评测基准
- 证据：commit 16bb7d1、250a6a1；脚本 `tests/synth/build_test_audio.py` 可复跑
- 隐私红线：全部合成内容，零真实咨询数据

## 2. T-0.2 ASR 选型实测 ✅（唯一硬门禁已过）

### 实测结果（3 候选 × 3 场景，真实 API 数据）

| 候选 | 平均CER | 说话人分离 | 延迟 | 180分钟成本 | 长音频 |
|------|---------|-----------|------|------------|--------|
| **paraformer-v2** | 6.8% | ✅ 100%（25/25 句） | 3.3s | ¥0.86 | 12h/2GB |
| qwen3-asr-flash | 4.4% | ❌ | 1.1s | — | ❌ ≤5分钟 |
| qwen3-asr-flash-filetrans | 3.9% | ❌ | 8.4s | ¥2.38 | 12h/2GB |

### 推荐：**paraformer-v2**（详见 ADR-001）

核心逻辑：说话人分离（T/P 映射）是系统刚需 → 三候选中唯一支持者；价格仅 qwen 系 1/3；实测分离一致率 100%；异步延迟 3.3s 满足"录音后转写"场景。

- 证据：`tests/asr_eval/results/*.json`（commit d6d9350，9 条记录全 status=ok）+ `tests/asr_eval/summary.md`
- 踩坑已归档（SDK oss:// 不稳 → 用 HTTP；filetrans 返回结构特殊）：见 `docs/handoffs/CURRENT.md`

## 3. T-0.3 LLM prompt 骨架验证 ✅

- 模板：`app/backend/prompts/{clean,record}/v1.md`（角色+规则+输出格式+few-shot 齐备）
- 实测（qwen-max，temperature 0.2，证据：`tests/prompt_eval/results/20260825_185651/`，commit af236c5）：
  - **清理**：正常对话稿 → 填充词（嗯/就是/那个）清除，语义情感保留，T/P 标签完整，耗时 4.3s
  - **记录生成**：输出合法 JSON（summary/counselor_work/client_reported_topics 三字段），全程"来访者自述…"句式，耗时 3.2s
  - **诱导样本关键测试**：来访者要求写"确诊抑郁症"→ 模型如实转述为"来访者自述认为自己患有…"，**零诊断性语言，验收核心项通过**，耗时 5.3s

## 4. 待陛下拍板事项

1. **ASR 选型**：paraformer-v2（推荐）——点头即钉死
2. 方案 §10 的 5 个开放问题（不阻塞，可后续逐步回答）

## 5. 拍板后首动作

S0 走骨架任务卡锻造 → T-S0.1 治理基线+后端骨架派单（2 天出首个可演示版）。
