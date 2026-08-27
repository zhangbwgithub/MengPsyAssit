# Task T-S1.5 自报：清洗模型切换 deepseek-v4-flash + clean prompt v4（拼音推理链）

## 做了什么

1. **清洗模型独立配置**：`Settings` 新增 `clean_llm_provider: str = "deepseek"`、`clean_llm_model: str = ""`，并仿 `_resolve_llm_model` 增加 `_resolve_clean_llm_model`（留空跟随 provider 默认）。`.env` 未加未改（默认值即生效）。
2. **clean/record 分路构造**：`routes.py` 新增 `_settings_for_clean`（用 `clean_llm_provider`/`clean_llm_model` 派生 Settings），clean 阶段走 `get_llm_provider(_settings_for_clean(settings))`；record 阶段继续 `get_llm_provider(settings)`（mimo 不动，T-S0.6 红线）。jobs 表 clean 行 provider 字段如实记 `deepseek`（`clean_llm.name`）。
3. **DeepseekLLM 关闭 thinking**：`openai_compat.py::complete()` 新增 `extra_body: dict | None = None` 合并进请求 body（MIMO/Qwen 不传不受影响）；`DeepseekLLM.complete()` 固定 `temperature=0.2` + `extra_body={"thinking": {"type": "disabled"}}`，调用方 temperature 被忽略，注释说明 DeepSeek API 硬约束。`health_check` 未改（仍 max_tokens=5）。
4. **clean prompt v4**：新增 `app/backend/prompts/clean/v4.md`——「上下文纠错」升级为拼音推理链表述（读音 → 同音/近音候选 → 按上下文选最有把握；读音差别过大或没把握保留原文，宁漏勿错），新增「指代纠错」独立规则（全文语境明确指代性别时按语境纠正他/她），其余规则与输出契约原样保留，示例区补「干喔→干呕」拼音推理链小示例。`prompts.py` clean 注册表切到 v4；v1/v2/v3 文件未动；`store_record` 的 `basic_info.prompt_version` 升 "v4"（该字段语义为 clean prompt 版本，record prompt 仍为 v2）。
5. **测试**：新增 `test_clean_llm_provider_defaults_to_deepseek`（clean 默认 deepseek + record 仍 mimo 防回归）、`test_clean_llm_model_explicit_override`、`test_deepseek_complete_disables_thinking_and_fixes_temperature`（httpx MockTransport 断言 body 含 `thinking.type=disabled` 且 `temperature=0.2`）、`test_clean_uses_deepseek_and_record_uses_mimo`（routes 层断言 clean 调用 deepseek-v4-flash、record 调用 mimo-v2.5-pro，jobs 表 provider 分别为 deepseek/mimo）；既有全链测试的 `prompt_version` 断言更新为 v4。

## 跑了什么命令 / 结果

| 命令 | 结果 |
|---|---|
| `HOME=/home/houmo .venv/bin/python -c "import psyapp.main"` | **PASS**（导入自检过） |
| `HOME=/home/houmo .venv/bin/python -m pytest app/backend/tests -q` | **PASS：44 passed** |
| `HOME=/home/houmo .venv/bin/ruff check app/backend` | **PASS：All checks passed!** |
| `npm --prefix app/frontend run build` | **PASS**（✓ built in 375ms） |
| clean prompt v4 加载探针（render_prompt + clean settings 派生 + 工厂类型） | **PASS**（含「拼音推理链」与「Prompt v4」，派生后工厂返回 DeepseekLLM） |

## 逐条对照验收标准

1. pytest 全过 + ruff + 导入自检 + 前端构建：**PASS**（44 passed / All checks passed / import OK / vite build OK）。
2. 请求 body 断言单测过（thinking disabled + temp 0.2）：**PASS**（`test_deepseek_complete_disables_thinking_and_fixes_temperature`，httpx MockTransport，无真实 API 调用）。
3. 真实端到端（陛下 56 段音频重跑，clean 走 deepseek-v4-flash，会话 done、重组正确、他/她纠错生效）：**NOT RUN**（大统领执行）。
4. 耗时对比（同音频 clean 耗时对比基线 293.8s，记录在自报/台账）：**NOT RUN**（大统领执行）。
5. 自报在 `docs/handoffs/task-T-S1.5-self-report.md`：**PASS**（本文件）。

## 说明与遗留

- 未 merge、未 push、未打 tag、未碰 `.env`；未改 record 阶段模型与 prompt（record/v2.md 未动）；未引新依赖；未改前端与 API 契约；未动 `tests/audio/`、`tests/golden/`、`prompts/clean/v1~v3.md`。
- `store_record.basic_info.prompt_version` 按任务卡升为 "v4"；其语义为 clean prompt 版本（`scripts/build_examples.py` 与前端均按「清理提示词」展示），record prompt 实际仍走 `record/v2.md`。
- `git diff` 自查范围：`config.py`、`routes.py`、`providers/openai_compat.py`、`providers/deepseek.py`、`prompts.py`、`services.py`、`tests/test_providers.py`、`tests/test_sessions.py`、新增 `prompts/clean/v4.md` 与本自报；`docs/handoffs/CURRENT.md` 为工作区既有改动，未纳入本次提交。
