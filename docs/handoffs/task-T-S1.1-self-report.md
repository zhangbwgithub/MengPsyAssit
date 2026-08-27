# Task T-S1.1 自报：角色分离重构——代号转写 + LLM 角色判定 + 气泡着色

## 做了什么

1. **后端移除 speaker_zero 全链路**：
   - `routes.py`：`POST /sessions` 删除 `speaker_zero` Form 参数与 422 校验；后台任务调用不再传该参数。
   - `services.py`：`run_background_pipeline` 签名去掉 `speaker_zero`。
   - `enums.py`：`Speaker` 类替换为 `SpeakerCode`（仅 UNKNOWN="U"）与 `Role`（T/P，供 role 列校验）。移除 T/P 预设映射枚举。
   - `segments.py`：删除 `apply_speaker_mapping`，新增 `assign_speaker_codes`——按 ASR speaker_id 首现序分配代号 A/B/C…；`build_transcript_lines` 输出改为 `代号: 文本`；新增 `build_cleaned_text` 用 `role_label: cleaned_content` 逐行拼 record 输入。
2. **clean 阶段升级为「清理+角色判定」**：
   - `models.py`：Segment 新增 `role`(String(1), nullable)、`role_label`(String(16), nullable)、`cleaned_content`(Text, nullable)；`speaker` 放宽为 String(8)。
   - `services.py`：新增 `parse_clean_json`（剥 ```json 围栏 + 严格校验 roles/cleaned 顶层结构）与 `_apply_clean_result`（校验 roles 覆盖全部代号、role∈{T,P}、cleaned seq 0..n-1 对齐、每段 text 非空，再写回 role/role_label/cleaned_content）；`_clean_transcript` 改为解析 JSON、写回 segments、返回 `build_cleaned_text`；坏 JSON/缺角色/seq 不齐 → 重试 1 次，仍失败标 `clean` job failed、session failed（与既有重试结构一致）。
   - `sessions.cleaned_text` 仍生成（`咨询师: …` / `来访者: …` 逐行拼接）。
3. **Prompt v2**：新增 `app/backend/prompts/clean/v2.md`、`record/v2.md`（自含示例，v1 文件未动）；`prompts.py` 注册表切到 v2；`store_record` 的 `basic_info.prompt_version` 升为 "v2"。
4. **前端气泡重构**：删除说话人映射单选区与 `speakerZero` 状态/提交字段；气泡单一来源 segments，文本优先 `cleaned_content` 否则 `content`；标签有 `role_label` 显示之，否则「说话人 A」式；按代号首现序分配 6 色调色板（蓝/绿/琥珀/紫/玫红/青，浅背景+同色系边框+深色文字），内联 style 着色；**对齐策略：role=T 靠左、role=P 靠右、未判定居中**（本卡已定，自报说明）。状态提示「正在转写与生成记录…」保留；记录卡片渲染不动（版本号自动跟随 v2）。
5. **测试**：
   - `test_sessions.py` 重写：FakeCleanLLM 改发出 v2 JSON；`test_upload_full_chain_*` 断言代号 {A,B}、role/role_label/cleaned_content、cleaned_text、prompt_version=v2；新增 `test_upload_ignores_extra_form_fields`（旧映射字段忽略）、`test_three_speaker_role_assignment`（3 代号 A/B/C + 同角色多人标签）、`test_clean_bad_json_retries_then_failed`、`test_clean_missing_speaker_code_retries_then_failed`、`test_clean_returns_fields_null_before_clean_stage`（GET 三新字段为 null）。
   - `test_db.py` 新增 `test_init_db_heals_missing_segment_columns`（验证旧 segments 表自动补齐 role/role_label/cleaned_content）。
6. **e2e**：`smoke_all.sh` 去掉 `-F speaker_zero=T`，断言改为「代号≥2 种 + role 含 T 和 P + 每段 cleaned_content 非空」；`smoke_main_chain.py` 同步去掉该字段并更新断言与文档说明。

## 跑了什么命令 / 结果

| 命令 | 结果 |
|---|---|
| `HOME=/home/houmo /home/houmo/.local/bin/uv pip install -p .venv -e "app/backend[dev]"` | PASS（psychapp 重装成功） |
| `.venv/bin/python -c "import psyapp.main"` | PASS（导入自检过） |
| `.venv/bin/python -m pytest app/backend/tests -q` | **PASS：33 passed** |
| `.venv/bin/ruff check app/backend` | **PASS：All checks passed!** |
| `cd app/frontend && npm run build` | **PASS**（✓ built，dist 生成） |
| `bash -n tests/e2e/smoke_all.sh` | PASS（shell 语法过） |
| `.venv/bin/python -m py_compile tests/e2e/smoke_main_chain.py` | PASS |
| `git grep -n "speaker_zero" -- ':!docs/handoffs' ':!docs/feedback.md' ':!docs/progress' ':!tests/e2e/results'` | **PASS：无残留** |

## 逐条对照验收标准

1. pytest 全过 + ruff 干净 + 导入自检过：**PASS**（见上表，33 passed / All checks passed / import OK）。
2. `POST /sessions` 不带旧映射参数正常受理、带了也不报错：**PASS**（`test_upload_full_chain_*` 不带参数走通；`test_upload_ignores_extra_form_fields` 带 `P` 仍 200 且代号按首现序分配）。
3. 真实端到端（01 号合成音频 → done；代号 A/B、role 判定 T+P 各至少 1、cleaned_content 非空、记录三字段齐全）：**NOT RUN**（大统领实测，本卡不跑真实网络链路）。
4. 单测覆盖 3 代号场景且过：**PASS**（`test_three_speaker_role_assignment`，代号 ["A","B","C","B"]，role {A:T,B:P,C:T}，标签 A=咨询师A/C=咨询师B）。
5. 前端构建成功 + 浏览器实测（无映射单选/每人一色/角色标签/375px 不破版）：构建 **PASS**；浏览器实测 **NOT RUN**（大统领 headless Chrome 复验）。
6. `git grep -n "speaker_zero"` 无残留：**PASS**（代码/前端/e2e 均无，仅保留 docs 历史任务卡与反馈台账原文）。
7. 本自报：**PASS**（本文件，逐条报 PASS/FAIL/NOT RUN）。

## 说明与遗留

- 未判定角色的气泡对齐选用「居中」（决策 5 允许二选一，本卡选居中并在代码注释注明：T 靠左 / P 靠右 / 未判定居中）。
- `docs/handoffs/CURRENT.md` 在本次会话期间出现大统领侧并发更新（非本卡范围），已保持原样未纳入本卡改动；提交前以 `git diff` 复核只含本卡范围变更。
- 未 merge、未 push、未打 tag、未碰 `.env`、未动 `tests/audio/`、`tests/golden/`、`app/backend/prompts/{clean,record}/v1.md`。
