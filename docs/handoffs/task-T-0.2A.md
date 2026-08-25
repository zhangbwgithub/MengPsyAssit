# 任务卡 T-0.2A：ASR 选型评测脚本框架（纯编写，禁止调用 API）

## 背景与契约

项目「咨询记录助手」（心理咨询录音 → 转写 → 整理），位于 /home/houmo/meng/MengPsyAssit。
当前处于 P0 技术验证阶段：需要实测比较两个 DashScope ASR 候选，为选型提供真实数据（字错率、说话人分离准确率、延迟）。
本任务**只编写评测脚本框架**，实测执行由编排方（大统领）后续运行，你不执行评测、不调用任何付费 API。

测试素材已就绪（勿改动）：
- 音频：`tests/audio/01_normal_dialogue.wav`（43.38s）、`tests/audio/02_overlap_interruption.wav`（18.7s）、`tests/audio/03_long_pauses.wav`（41.58s）。均为 16kHz 单声道 16bit PCM WAV，双音色合成（T=男声咨询师，P=女声来访者）。
- 黄金基准：`tests/golden/<同名>.json`，结构：
  ```
  {"scenario": ..., "turns": [{"idx":0,"speaker":"T","role":"counselor","text":"...","start":0.0,"end":3.44}, ...], "transcript": "T: ...\nP: ..."}
  ```
  speaker 取值 "T"/"P"。注意 golden 的 start/end 是拼接时间线的计划值，有 ±0.5s 左右的误差，是约值。

## 候选 ASR 与 API 事实（已调研核实，照此实现）

### 候选 1：paraformer-v2 录音文件识别（异步任务，支持说话人分离）
- DashScope Python SDK：`dashscope.audio.asr.Transcription`
  - `Transcription.async_call(model='paraformer-v2', file_urls=[url], language_hints=['zh','en'], diarization_enabled=True, speaker_count=2)`
  - `Transcription.wait(task=resp)` 轮询直到 SUCCEEDED/FAILED
  - 结果 output.results 每个文件含 `transcription_url`（需再下载该 JSON），内部结构 `transcripts[0].sentences[]`，每句字段：`text`、`begin_time`(ms)、`end_time`(ms)、`speaker_id`(int)
- HTTP 等价：POST https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription ，Header `Authorization: Bearer KEY` + `X-DashScope-Async: enable`，body `{"model":"paraformer-v2","input":{"file_urls":[...]},"parameters":{"diarization_enabled":true,"speaker_count":2,"language_hints":["zh","en"]}}`；响应含 `output.task_id`；轮询 GET `/api/v1/tasks/{task_id}`。
- ⚠️ 关键约束：file_urls 必须是**公网可访问 URL**，不支持本地文件。这是产品事实。脚本按 URL 输入实现即可（执行时编排方会提供托管方案，若最终无法托管会在报告中降级说明，不是你要解决的问题）。

### 候选 2：qwen3-asr-flash（同步，多模态 chat 风格）
- DashScope SDK：`dashscope.MultiModalConversation.call(model='qwen3-asr-flash', messages=[{"role":"user","content":[{"audio": "<本地文件绝对路径 或 URL 或 base64 data URI>"}]}], result_format='message')`
  - SDK 模式下 audio 字段支持**本地文件绝对路径**。
- 返回整段纯文本（无句级时间戳、无说话人分离）——记录此事实到结果中（speaker 评估只能得 N/A 或整段对比）。
- HTTP 等价（OpenAI 兼容风格，audio 需 base64 data URI）：POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions，body `{"model":"qwen3-asr-flash","messages":[{"role":"user","content":[{"type":"input_audio","input_audio":{"data":"data:audio/wav;base64,<b64>"}}]}]}`
- 限流：100 RPM。

### API Key
从环境变量 `DASHSCOPE_API_KEY` 读取。脚本里**绝不硬编码**，读取不到时报清晰错误并退出码 2。

## 要求

### 正面清单
1. 新建目录 `tests/asr_eval/`，结构：
   ```
   tests/asr_eval/
   ├── run_eval.py        # CLI 入口
   ├── cer.py             # 纯标准库 CER：字符级 Levenshtein 编辑距离 / max(len(ref),1)，中文按字符、去空白与标点后再算
   ├── providers/
   │   ├── __init__.py
   │   ├── paraformer.py  # 候选1封装
   │   └── qwen_asr.py    # 候选2封装
   └── README.md          # 用法说明 + 两候选的已知能力差异表
   ```
2. `run_eval.py` CLI：
   - `--model paraformer|qwen3-asr|all`（默认 all）
   - `--audio`（可多次，默认 tests/audio/ 下全部三个 wav）
   - `--out-dir`（默认 tests/asr_eval/results/）
   - `--dry-run`：只打印将要执行的调用计划（模型、音频、参数、预估请求数），不发起任何网络请求
3. 每个 (模型, 音频) 组合产出一条结果记录，字段：
   `model, audio, status(ok|error), latency_s(API 往返耗时), full_text, sentences[{text, begin_ms, end_ms, speaker_id|null}], cer(对黄金全文), speaker_stats{matched, mismatched, unknown}|null, error(出错时)`
   全部结果写入 `<out-dir>/<模型名>_results.json`（UTF-8、indent=2）。
4. CER 计算：ref=黄金 transcript（按 "T: xxx" 各行取文本拼接），hyp=ASR full_text；归一化=去空白与中英文标点；`cer.py` 必须有独立可测函数 `normalize(s)` 与 `cer(ref, hyp)`。
5. 说话人分离评估（仅 paraformer 适用）：把 ASR 的 sentences 按时间中点匹配到黄金 turns（找时间交叠最大的 turn），speaker_id 与黄金 speaker 的一致性统计为 matched/mismatched/unknown（无法匹配时）；注意黄金只有 T/P 两个标签而 ASR 的 speaker_id 是 0/1 等整数——统计"同一 speaker_id 是否稳定对应同一黄金标签"（先建立多数投票映射，再算一致率），把这个映射和一致率写进结果。
6. `cer.py` 附带至少 5 条断言的自检（`python3 cer.py` 直接跑，含：完全一致=0、完全不同>0、空 hyp、含标点归一、中英混合），不依赖 pytest。
7. 网络层：若本机已装 `dashscope` SDK（先探测 `import dashscope` 是否成功）则用 SDK；否则回退到纯标准库 `urllib.request` 实现同样的 HTTP 调用。两条路径都要写。

### 反面清单（不要做）
- ❌ 不要实际调用任何 DashScope API（包括"测试一下连通性"）
- ❌ 不要修改 tests/audio/、tests/golden/、tests/synth/、docs/ 下任何文件
- ❌ 不要创建/修改 .env，不要安装系统级依赖（若判断需要 dashscope 包，只在 README 里写安装命令建议，用 `uv` 或项目内 .venv，不要实际执行安装）
- ❌ 不要实现上传/托管音频的功能
- ❌ 不要引入 jiwer 等第三方评测库，CER 必须纯标准库

## 验收标准（大统领将逐条判定）
1. `tests/asr_eval/` 目录结构齐全（上述 6 类文件）
2. `python3 tests/asr_eval/cer.py` 自检全过
3. `python3 tests/asr_eval/run_eval.py --dry-run` 正常输出计划、退出码 0、全程无网络请求
4. `python3 -m py_compile` 对所有新 .py 文件通过
5. 代码中无硬编码 API key、无未处理的 TODO 占位
6. git 提交一条：`[T-0.2A] feat: ASR选型评测脚本框架 (paraformer-v2 + qwen3-asr-flash)`
7. ruff 检查（若本机有）新文件无 E/F 级错误

## 技术约束
- Python 3.11（系统 python3），新代码尽量纯标准库；dashscope SDK 路径作为可选增强
- 所有文件输出 UTF-8
- 仓库根：/home/houmo/meng/MengPsyAssit（所有相对路径以此为根）
- 当前在 main 分支上直接提交即可（P0 阶段允许），提交身份使用仓库已配置的 git 身份
