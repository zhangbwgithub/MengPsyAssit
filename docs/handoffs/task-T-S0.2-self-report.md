# T-S0.2 自报：Provider 接口 + 单一实现

## 做了什么

- `psyapp/config.py`：Settings 新增 `asr_provider`（默认 paraformer）、`llm_provider`（默认 qwen）、`llm_model`（默认 qwen-max）。
- `psyapp/providers/base.py`：ASRProvider / LLMProvider 抽象接口（签名按任务卡一次定型）、`Segment` / `TranscriptResult` dataclass、`ProviderError`。
- `psyapp/providers/paraformer.py`：`DashScopeParaformer` 纯 HTTP 实现（httpx）——`dashscope oss.upload` 子进程上传取 oss:// URL → 提交异步任务（`X-DashScope-Async` + `X-DashScope-OssResourceResolve` 头，diarization + speaker_count + language_hints）→ 3s 轮询 / 15min 超时 → 下载 transcription_url 解析为 Segment（speaker=speaker_id 字符串化，不做"谁是 T"映射）。health_check 策略：GET 不存在的 task_id，401/403 判不可用（零费用探测）。
- `psyapp/providers/qwen.py`：`QwenLLM` 走 compatible-mode chat/completions；schema_hint 拼入 system 提示；health_check 为一次最小 completion（max_tokens=5）。
- `psyapp/providers/__init__.py`：`get_asr_provider(settings)` / `get_llm_provider(settings)` 工厂，未知值抛 ValueError。
- 单测 `app/backend/tests/test_providers.py`：9 个用例（工厂默认选择/未知 ASR/未知 LLM/空 key 抛错、transcription JSON 解析字段断言、空 transcripts、schema_hint 消息组装×3）。
- 冒烟 `tests/provider_eval/smoke_providers.py` + README：真实跑 ASR（01_normal_dialogue.wav）与 LLM，结果落盘 `tests/provider_eval/results/20260826-082933/`（asr_transcript.json / llm_completion.json / http_trace.jsonl，不含任何请求头）。
- `.gitignore`：补 `tests/provider_eval/results/`（与 asr_eval 同策略，证据用 `git add -f` 强制入库）。

## 跑了什么 / 结果

- `.venv/bin/python -m pytest app/backend/tests -q` → **13 passed**（PASS）
- `.venv/bin/ruff check app/backend` → **All checks passed**（PASS）
- `.venv/bin/python tests/provider_eval/smoke_providers.py` → 退出码 0（PASS）：
  - ASR health_check=True；段数=11（>10 ✓），说话人=['0','1']（≥2 ✓），耗时 3.8s
  - LLM health_check=True；qwen-max 中文响应非空 ✓，耗时 1.3s
  - http_trace.jsonl 记录 7 次真实 API 往返（health_check/提交/轮询×2/transcription_url 下载/LLM×2）
- 密钥检查：`grep -r "sk-" tests/provider_eval/results/` 零命中；trace 不含 Authorization/Bearer（PASS）

## 未做（按反面清单）

未实现第二个 provider；未写业务 API 端点、未动 main 路由；未做说话人映射/文本清理；未用 dashscope SDK 做转写；未动 tests/audio/、tests/golden/、prompts/。

自报不作数，以大统领实测为准。
