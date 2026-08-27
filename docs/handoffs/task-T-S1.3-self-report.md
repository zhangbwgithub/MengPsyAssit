# Task T-S1.3 自报：语义重拼清洗（碎片合并 + 上下文纠错 + 分块提速 + 进度条）

## 做了什么

1. **clean v3 契约（语义重拼，段落不再 1:1）**：新增 `app/backend/prompts/clean/v3.md`（蒸馏 zxkane v1.7.1 Phase 2+3 方法论：同人碎片合并、上下文纠错含「他→她」指代纠正、去填充词/合并口吃、修语法但保原意不新增、source_seqs 不重不漏、只输出 JSON，自带完整示例）；`prompts.py` 注册表 clean 由 v2 切换到 v3，`v1/v2、record` 均未动。
2. **语义重拼写回**：`services.py` 重写 clean 校验/写回——`validate_clean_result`（roles 覆盖全部代号且 role∈{T,P}、paragraph speaker 已知代号且 text 非空、所有 `source_seqs` 拼接后恰好等于 `[0..n-1]` 不重不漏不乱序）；`_replace_segments_with_paragraphs` 清空旧段后按重组段落重建（seq 重排、speaker/role/role_label/cleaned_content、start_ms/end_ms 取 source_seqs 首/末段、content 保留原文本换行拼接）。坏 JSON/校验失败重试 1 次（同现状）。
3. **raw_transcript 审计底稿**：`Session` 新增 `raw_transcript`（Text, nullable），清理前把原始转写稿（`代号: 文本` 逐行）先落库——即便 clean 失败也不丢；`db._heal_missing_columns` 自动补齐旧库缺列。
4. **分块提速**：≤60 段单次调用（现状路径）；>60 段按说话人轮换边界（连续同人 run 之间）切块、每块 ≤50 段、连续同人超 50 段硬切；每块独立调用 clean v3，角色冲突取首次出现块判定，paragraphs 顺序拼接、source_seqs 映射回全局 seq；任一块重试后仍失败则整个 clean 失败。
5. **前端进度条 + 转写中间态简化**：上传卡片内新增三阶段进度条（转写 → 清理与角色判定 → 生成记录），纯前端由 `segments/record/status` 推导，done 全点亮、failed 定位失败阶段标红；阶段2（有 segments 未判定角色且未 done）气泡紧凑化（小内边距、无时间戳、只显「说话人 A」+文本），标题旁标注「原始转写，正在按语义清理…」，完成后恢复每人一色+T左P右+时间戳。375px 可换行不破版，无新依赖。
6. **测试**：原 v2 契约测试全部迁移到 v3；新增碎片合并（3 段合 1 + 他→她）、source_seqs 缺段/重复校验失败、>60 段分块（fake LLM 断言调用 2 次且 seq 映射回全局）、raw_transcript 落库（成功+失败路径）、列自愈（test_db 补 session 缺列场景 raw_transcript 断言）。

## 跑了什么命令 / 结果

| 命令 | 结果 |
|---|---|
| `HOME=/home/houmo .venv/bin/python -c "import psyapp.main"` | PASS（导入自检过） |
| `HOME=/home/houmo .venv/bin/python -m pytest app/backend/tests -q` | **PASS：39 passed**（0.10s 量级/用例，全 green） |
| `HOME=/home/houmo .venv/bin/ruff check app/backend` | **PASS：All checks passed!** |
| `npm --prefix app/frontend run build` | **PASS**（✓ built in ~375ms） |
| `_split_clean_chunks` 边界探针（61 交替/55 连人硬切/中间单次轮换） | PASS（全部块 ≤50，交替 61→2 块） |

## 逐条对照验收标准

1. pytest 全过 + ruff 干净 + 导入自检：**PASS**（39 passed / All checks passed / import OK）。
2. 单测：碎片合并（3 段合 1）**PASS**（`test_clean_merges_same_speaker_fragments_into_one_paragraph`）；source_seqs 缺段/重复校验失败 **PASS**（`test_clean_source_seqs_missing_or_duplicate_rejected`）；分块（>60 段 → ≥2 次调用且合并正确）**PASS**（`test_clean_chunks_over_60_segments_makes_multiple_calls`，61 段调用 2 次）；raw_transcript 落库 **PASS**（`test_upload_full_chain_*` + `test_clean_bad_json_retries_then_failed` 失败路径）；列自愈 **PASS**（`test_init_db_heals_missing_columns_in_old_schema` 补 raw_transcript 断言）。
3. 前端构建成功 **PASS**；浏览器实测进度条三阶段推进、中间态紧凑气泡、完成态每人一色：**NOT RUN**（大统领跑）。
4. 陛下真实音频重跑（01:03/01:07 拆句合并、碎片减少、「他/她」纠错抽查）：**NOT RUN**（大统领执行）。
5. 耗时观察（分块后 59 段 clean jobs 时间戳，不劣于单块 125s）：**NOT RUN**（大统领执行；59 ≤ 60，本卡分块路径不触发，仍走单次调用）。
6. 自报在 `docs/handoffs/task-T-S1.3-self-report.md`：**PASS**（本文件，逐条 PASS/FAIL/NOT RUN）。

## 说明与遗留

- 59 段实证场景 ≤60 阈值走单次调用（现状路径），分块提速主要面向超 60 段长会谈；单次调用的耗时与旧路径同量级（同一 LLM 调用）。
- `_split_clean_chunks` 在「>60 段且单轮硬切」的最坏情况可产生 3 块（500 段问题留待未来，S0 不做）；本卡场景每块 ≤50 段。
- source_seqs 严格要求「拼接后恰好等于 0..n-1」，因此 LLM 跨说话人重排会校验失败并重试——契约本身要求全局顺序不减（决策 1）。
- 前端无测试框架，进度条/紧凑气泡无自动化覆盖（浏览器实测留大统领）。
- 未 merge、未 push、未打 tag、未碰 `.env`；未动 `tests/audio/`、`tests/golden/`、`prompts/{clean,record}/v1.md`、`prompts/clean/v2.md`、record prompt、provider 实现；未改 API 响应结构（仅 segments 数量为重组后结果、sessions 表新增 nullable 列）。
