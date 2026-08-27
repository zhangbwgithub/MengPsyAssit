# Task T-S1.5b: record 阶段也切换 deepseek-v4-flash

## 背景与契约

陛下追加旨意（2026-08-28，口头指令，记录在案）：「record 阶段也可以试一下 deepseek-v4-flash」。

T-S1.5 已在 `task/t-s1.5-deepseek-clean` 分支完成（clean 阶段独立切 deepseek-v4-flash，commit `7b8ea11`）。本卡为**同分支增量补丁**：把 record 阶段也切过去。

**你不 merge、不 push、不打 tag**；自报追加到 `docs/handoffs/task-T-S1.5-self-report.md` 末尾（新增「T-S1.5b 追加」小节）。

## 输入与环境事实

- 分支：继续在 `task/t-s1.5-deepseek-clean` 上（工作区干净，直接提交）。
- T-S1.5 已建模式：`Settings.clean_llm_provider/clean_llm_model` + `routes.py::_settings_for_clean` + `DeepseekLLM.complete()` 固定关 thinking / temp 0.2。
- record 阶段现状：用全局 `llm_provider`（mimo）+ `llm_model`（mimo-v2.5-pro），prompt `record/v2.md` 不动。

## 钉死的决策

1. **仿 clean 模式加 record 配置**：`Settings` 新增 `record_llm_provider: str = "deepseek"`、`record_llm_model: str = ""`（validator 解析仿现有逻辑）。
2. `routes.py` 的 record 阶段用 `record_llm_provider/record_llm_model` 构造 LLM（可复用/扩展 `_settings_for_clean` 为通用辅助，或对称写一个，自选最简）。
3. **`llm_provider`（全局，mimo）保留为兜底/未来用途**，不删除；`.env` 不加不改。
4. `jobs` 表 record 行的 `provider` 字段如实记 `deepseek`。
5. record prompt（`record/v2.md`）**不动**；`store_record` 的 `basic_info.model` 字段如实反映实际模型（检查现有实现是否自动跟随，若写死则修正）。
6. 测试：更新/新增 routes 层断言——record=deepseek、jobs record 行 provider=deepseek；clean 断言保持不变。

## 禁止清单

- 不动 clean 阶段任何代码（已验收通过）。
- 不动 prompt 文件、前端、`.env`；不引依赖。
- 不真实调外部 API 跑测试；不 merge、不 push、不打 tag。

## 验收标准（大统领逐条实测）

1. pytest 全过 + ruff + 导入自检。
2. **真实端到端**（大统领执行）：陛下 56 段音频重跑，clean+record 全走 deepseek-v4-flash，会话 done、记录三字段齐全。
3. **耗时对比**（大统领执行）：clean/record 各阶段耗时对比基线（MIMO：clean 293.8s / record ~100s）。
4. 自报追加小节。

## 门禁

构建 → 测试 → 静态；提交前 `git diff` 自查只含本卡范围。提交消息：`[T-S1.5b] feat: 描述`。
