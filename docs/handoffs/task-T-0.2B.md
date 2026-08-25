# 任务卡 T-0.2B：ASR 评测框架扩展第三候选 + 实际执行评测

## 背景与契约

你在上一个任务（T-0.2A，git 提交 8637911）中已建好 `tests/asr_eval/` 评测框架（paraformer-v2 + qwen3-asr-flash 两个候选）。现在分两步：
1. **扩展**：新增第三候选 `qwen3-asr-flash-filetrans`（Qwen 系的长音频文件转写版，本项目必须支持 180 分钟录音，短音频版不够用）
2. **执行**：用本机环境实际跑完全部评测，产出真实结果数据

仓库根：/home/houmo/meng/MengPsyAssit（所有相对路径以此为根）。

## 输入与环境事实（已核实）

- 项目 venv：`.venv/bin/python`（Python 3.11，已装 dashscope 1.27.1）。**执行评测一律用 `.venv/bin/python` 和 `.venv/bin/dashscope`**
- API Key：环境变量 `DASHSCOPE_API_KEY`（启动命令会注入，你代码里只读环境变量，绝不硬编码、绝不打印明文）
- 音频素材（勿改动）：`tests/audio/0{1,2,3}_*.wav`，16kHz 单声道 16bit WAV，时长 43.38/18.70/41.58s
- 黄金基准：`tests/golden/<同名>.json`（结构同前：turns[].speaker∈{T,P}, text, start, end）
- 本机无公网静态托管；音频上传用 DashScope 官方临时存储（下述流程）

## 新候选 API 事实（官方文档核实）

### qwen3-asr-flash-filetrans（异步任务，支持句级时间戳，不支持说话人分离）
- HTTP：POST https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription
  - Header：`Authorization: Bearer KEY`、`Content-Type: application/json`、`X-DashScope-Async: enable`
  - body：`{"model": "qwen3-asr-flash-filetrans", "input": {"file_url": "<URL>"}, "parameters": {"language": "zh"}}`
  - ⚠️ 注意字段是 `file_url`（单数），与 paraformer 的 `file_urls`（复数数组）不同
- 轮询：GET https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}（同 paraformer）
- 结果结构：output.results[].transcription_url → 下载 JSON，`transcripts[0].sentences[]`，字段 `text`/`begin_time`(ms)/`end_time`(ms)；**无 speaker_id**（该模型不支持说话人分离，官方模型页明确）
- SDK 等价：`dashscope.audio.asr.Transcription.async_call(model='qwen3-asr-flash-filetrans', file_urls=[url], language='zh')`（SDK 参数名可能统一为 file_urls，若 SDK 报错再回退 HTTP）

### 音频上传（官方临时存储，48h 有效）
用项目 venv 的 CLI：
```bash
.venv/bin/dashscope oss.upload --model paraformer-v2 --file tests/audio/01_normal_dialogue.wav
```
输出形如 `Uploaded oss url: oss://dashscope-instant/xxx/...`。拿到 oss:// URL 后：
- SDK 调用直接传 oss:// URL（SDK 自动处理 `X-DashScope-OssResourceResolve` 头）
- 纯 HTTP 路径则必须加请求头 `X-DashScope-OssResourceResolve: enable`
上传一次即可供三个候选共用。

## 要求

### 第一步：扩展框架
1. 新建 `tests/asr_eval/providers/qwen_asr_filetrans.py`：异步任务封装（结构仿照 paraformer.py），无说话人分离评估（speaker_stats 记为 `{"supported": false}`）
2. `run_eval.py` 注册第三候选：`--model` 可选值加 `qwen3-asr-flash-filetrans`，`all` 包含全部三个
3. paraformer 与 filetrans 两个 provider 增加本地文件自动上传能力：传入本地路径时，优先尝试 `.venv/bin/dashscope oss.upload`（subprocess），解析出 `oss://` URL 再调用；上传失败则报清晰错误退出
4. `--dry-run` 同步更新（显示三个候选）

### 第二步：实际执行
5. 用 `.venv/bin/python tests/asr_eval/run_eval.py --model all` 跑完全部 9 组（3 候选 × 3 音频）
   - paraformer 轮询排队可能需要数分钟，耐心等；单组超 10 分钟视为失败记录
   - 失败的组记录 error 字段，不要让单组失败拖垮整体
6. 检查 `tests/asr_eval/results/*.json` 完整（三组结果文件，每组 3 条记录）
7. 写 `tests/asr_eval/summary.md`：一张表汇总——每 (候选,音频) 的 CER、latency、说话人分离一致率（paraformer）、状态；再给一个候选横向对比小节（只摆数字和官方规格，不下最终选型结论——选型由编排方定夺）

### 反面清单
- ❌ 不修改 tests/audio/、tests/golden/、docs/
- ❌ 不写最终选型结论（那是编排方的活）
- ❌ 不在代码、输出、日志中出现 API key 明文
- ❌ 不安装新依赖（.venv 已有全部所需）
- ❌ 不删改已有的 T-0.2A 产出逻辑，只增补

## 验收标准（编排方逐条实测）
1. `--dry-run` 显示三个候选，退出码 0
2. `results/` 下三个候选的结果 JSON 齐全，共 9 条记录，每条有 status 字段
3. `summary.md` 存在，含 9 组数据的完整表格
4. 所有 CER/latency 数字来自真实 API 返回（抽查：结果文件里能找到 API 返回的原文痕迹，非手填）
5. `python3 -m py_compile` 新增文件通过
6. git 提交：`[T-0.2B] feat: ASR评测扩展filetrans候选+实测执行`（代码+结果一起提交；注意 results/ 已在 .gitignore，需 `git add -f tests/asr_eval/results/*.json tests/asr_eval/summary.md` 强制加入，这些是评测证据）
7. 全程零密钥泄露（结果 JSON 中不得出现 sk- 开头字符串）

## 技术约束
- 用 `.venv/bin/python` 执行评测（系统 python3 无 dashscope）
- 输出文件全部 UTF-8
- 提交身份用仓库已配置的 git 身份
