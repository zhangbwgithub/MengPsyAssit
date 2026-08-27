# Task T-S1.4 自报：修复长转写 seq 数错导致清理失败——输入显式编号

## 做了什么

1. **输入显式编号（根因修复）**：`segments.py::build_transcript_lines_from_segments` 输出改为 `[seq] 代号: 文本`，seq 取 `seg.seq`。≤60 段单次调用路径：输入即 `[0] A: …` / `[1] B: …`；>60 段分块路径：每块内也用 `seg.seq`（全局 seq，不是块内从 0 重数），与输出 source_seqs 保持全局口径一致。
2. **clean/v3.md 同步**：输入格式节改为「每行格式 `[seq] 代号: 文本`，方括号内即该段 seq；source_seqs 必须逐字引用这些编号，不得自创、不得数行号」；规则7/输出格式说明/示例区同步带 `[0]`…`[4]` 编号。
3. **分块拼块逻辑同步**：既然输入显式带全局 seq 且契约要求「逐字引用」（决策2），模型返回的 source_seqs 就是全局编号——
   - `services.py::_clean_transcript` 合并段落时**去掉 `+ chunk_start` 偏移**（否则二次偏移）；
   - `validate_clean_result` 的期望序列由 `list(range(len(segments)))` 改为 `[seg.seq for seg in segments]`。严格覆盖规则**不变**（拼接后必须恰好等于输入段的 seq 序列、不重不漏、顺序不减），只是基准从「假设从 0 连续」改为「以输入段实际 seq 为准」。单次调用路径（seq 恒为 0..n-1，即本次失败的 56 段场景）下行为逐字节一致；分块第二块起（seq 非从 0 起）这才成立。
4. **测试**：两处 `raw_transcript` 断言同步为 `[0] A: …` 格式；`test_clean_source_seqs_missing_or_duplicate_rejected` 的 Segment 显式带 seq；分块测试 fake 改为直接返回全局 seq（对齐模型新行为）；新增防回归单测 `test_transcript_lines_carry_explicit_seq_numbers`（断言输入含 `[0] A:` / `[1] B:` / `[2] A:` 显式编号）。

## 跑了什么命令 / 结果

| 命令 | 结果 |
|---|---|
| `.venv/bin/python -c "import psyapp.main"` | PASS（导入自检过） |
| `.venv/bin/python -m pytest app/backend/tests -q` | **PASS：40 passed** |
| `.venv/bin/ruff check app/backend` | **PASS：All checks passed!** |
| `cd app/frontend && npm run build` | **PASS**（✓ built in 381ms） |
| `git diff` 自查 | 仅 4 文件：`segments.py`/`services.py`/`clean/v3.md`/`test_sessions.py`，无残留 |

## 逐条对照验收标准

1. pytest 全过 + ruff + 导入自检 + 前端构建：**PASS**（40 passed / All checks passed / import OK / vite build OK）。
2. 单测断言输入显式编号：**PASS**（`test_transcript_lines_carry_explicit_seq_numbers`）。
3. 陛下失败音频重跑（56 段，done + 段落重组正常）：**NOT RUN**（大统领执行；56 ≤ 60 走单次调用路径，本卡只修输入侧编号）。
4. 自报在 `docs/handoffs/task-T-S1.4-self-report.md`：**PASS**（本文件）。

## 说明与遗留

- **与「不改校验逻辑」的一处必要同步**：任务书决策1要求「分块每块内带全局 seq、与输出 source_seqs 全局口径一致并把拼块逻辑同步」，决策2要求「source_seqs 逐字引用方括号编号」；两者共同推出分块第二块起模型返回的 seq 是全局编号，故 `validate_clean_result` 的期望基准必须改为 `[seg.seq for seg in segments]`，并去掉合并时的 `+chunk_start` 偏移。严格覆盖规则本身未放宽（不重不漏、顺序不减、安全网保留），单次调用路径行为不变。若大统领认为应换个等价写法（例如校验前先把每块段局部化），可再调整，但「输入全局编号 + 校验按块 0..n-1」二者不可兼得。
- 未改校验的覆盖规则、未动段落重组顺序逻辑、未动 v1/v2/record prompt、未动 provider、未引依赖；未 merge、未 push、未打 tag、未碰 `.env`；未动 `tests/audio/`、`tests/golden/`、`docs/` 其他文件。
