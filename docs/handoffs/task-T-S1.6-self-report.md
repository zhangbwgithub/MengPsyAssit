# Task T-S1.6 自报：双模式管线——Qwen3.5-Omni-Plus 多模态直转 + 上传可选模式

## 做了什么

1. **omni provider**：新增 `app/backend/src/psyapp/providers/omni.py`。
   - `QwenOmniLLM`（base_url=`https://dashscope.aliyuncs.com/compatible-mode/v1`、model=`qwen3.5-omni-plus`、key env=`DASHSCOPE_API_KEY`），复用 `OpenAICompatLLM` 的 HTTP 层（Bearer 鉴权、错误不泄露 key），httpx timeout 300s。
   - `transcribe_audio(audio_path, prompt)`：读文件 → base64 → 按探针结构组多模态请求（`content=[input_audio, text]`、`modalities=["text"]`、`enable_thinking=false`、非流式），返回 `choices[0].message.content` 文本；`input_audio.format` 跟随真实文件后缀（mp3/wav/m4a/opus/flac）。
   - `OMNI_TRANSCRIBE_PROMPT`：照抄探针 prompt，未改写。
   - `parse_omni_transcript`：逐行解析轮次文本；先按 `\t` 切三字段，切不开按空白切，再切不开按「序号 角色：内容」冒号容错；空行/不可解析行跳过；咨询师→T、来访者→P，其他角色文本归 P 兜底并保留原词为 `role_label`；speaker 代号按角色标签首现序 A/B/C；`content=cleaned_content`、`start_ms/end_ms=None`、`seq` 从 0 重排。
2. **双模式管线分叉**：`services.py::run_background_pipeline` 新增关键字参数 `pipeline_mode`（默认 `"asr"`，旧调用方不受影响）与 `omni`。
   - omni 路径：transcribe job（provider=`qwen3.5-omni-plus`）内调 `QwenOmniLLM.transcribe_audio`；`raw_transcript` 存 omni 原始输出；解析出 0 轮视为失败重试 1 次，仍失败 → session failed；**不建 clean job**；`cleaned_text` 用 `build_cleaned_text` 拼 segments；record 阶段照旧（deepseek，坏 JSON 重试 1 次）。
   - asr 路径：现状完全不变（paraformer → clean v4 → record，分块/校验/重试逻辑未动）。
3. **API 契约**：`routes.py::POST /sessions` 新增可选表单字段 `mode`（`"omni"`|`"asr"`，默认 `"omni"`）；非法值 → 400 `validation_error`。`Session` 新增 `pipeline_mode` 列（`String(8)`，nullable，SQLite 自愈机制自动补列）。`GET /sessions/{id}` 返回 `pipeline_mode` 与 `model_display`（omni → `qwen3.5-omni-plus`；asr → `paraformer-v2 + deepseek-v4-flash`），omni 模式 segments 的 `start_ms/end_ms` 返回 `null`。
4. **segments 落库**：`segments.py` 新增 `apply_omni_segments_to_session`——按 seq 重排落库，保留解析好的 speaker/role/role_label/cleaned_content，时间戳存 0（DB 列非空，API 层返回 null）。
5. **前端**：`App.vue` 上传卡片新增双模式 radio（显式模型名，默认「多模态直转（推荐）」），上传带 `mode`；进度条按模式自适应（omni 两阶段「多模态直转 → 生成记录」，asr 维持三阶段）；omni 气泡不渲染时间戳行；对话稿标题与记录元信息显示 `model_display`；375px 下模式卡纵向堆叠。
6. **测试**：新增 `tests/test_omni_mode.py`（mode 默认 omni / 非法值 400 / 解析含冒号与空行 / 解析 0 轮重试失败 / `QwenOmniLLM` 请求结构断言，全部 monkeypatch，无真实 API）；`tests/test_sessions.py` 既有 asr 用例显式传 `mode=asr`（默认 omni 后的回归适配），并在全链测试中补 `pipeline_mode`/`model_display` 断言。

## 跑了什么命令 / 结果

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -c "import psyapp.main; import psyapp.providers.omni; print('import ok')"` | **PASS**（import ok） |
| `.venv/bin/python -m pytest app/backend/tests -q` | **PASS：54 passed** |
| `.venv/bin/ruff check app/backend` | **PASS：All checks passed!** |
| `cd app/frontend && npm run build` | **PASS**（vite build，约 382ms） |
| `git diff --check` | **PASS**（无 whitespace 错误） |

## 逐条对照验收标准

1. pytest 全过 + ruff + 导入自检 + 前端构建：**PASS**（54 passed / All checks passed / import ok / vite build ok）。
2. 浏览器实测（选「多模态直转」上传 01 号合成音频 → 两阶段进度 → 17 轮风格对话稿、模式/模型名显示正确）：**NOT RUN**（大统领执行；后端单测已覆盖默认 omni 成功路径与两阶段 job 结构）。
3. 陛下真实音频实测（omni 模式重跑 56 段音频）：**NOT RUN**（大统领执行）。
4. asr 模式回归（选 asr 模式上传 01 号音频仍走三段）：**NOT RUN**（大统领浏览器执行；后端 46 项 asr 回归用例已显式 `mode=asr` 全部通过）。
5. 自报在 `docs/handoffs/task-T-S1.6-self-report.md`：**PASS**（本文件）。

## 说明与遗留

- 未 merge、未 push、未打 tag、未碰 `.env`；未改 clean/record prompt、未改 asr 路径行为；未引新依赖（httpx 已有）；未把音频 base64 写日志（日志只记 session_id 与异常类型/信息，`openai_compat` 现有掩码/不泄 key 逻辑复用）。
- `git diff` 自查范围：`enums.py`、`models.py`、`routes.py`、`segments.py`、`services.py`、`providers/omni.py`（新增）、`tests/test_omni_mode.py`（新增）、`tests/test_sessions.py`、`app/frontend/src/App.vue` 与本自报；`app/frontend/dist/` 为 gitignore，构建产物不入本次提交。
- 一个实现取舍：任务卡探针示例 `input_audio.format` 为 `"mp3"`（探针音频是 mp3）；本实现按上传文件真实后缀映射 format，避免 wav/m4a 等被误标 mp3 导致真实音频实测失败（单测覆盖 `.wav` → `"wav"`）。
