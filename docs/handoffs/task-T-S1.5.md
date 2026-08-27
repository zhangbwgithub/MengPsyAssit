# Task T-S1.5: 清洗模型切换 deepseek-v4-flash + clean prompt v4（拼音推理链）

## 背景与契约

陛下指令（`docs/feedback.md` FB-005）：启用 DeepSeek-v4-flash 作为清洗模型改进现有工作流；同时吸收调研到的方法论（teamtee 拼音推理链纠错，Hermes skill `asr-transcript-cleanup` 已封装，可 `skill_view` 参考）。

**关键事实（大统领已实测验证，勿重复验证）：**
1. `.env` 已有 `DEEPSEEK_API_KEY`（可用，探针实测通过）；`providers/deepseek.py` 已接好，默认模型 `deepseek-v4-flash`。
2. **deepseek-v4-flash 是推理模型**：默认带 thinking 时 96% 输出是推理 tokens（3.0s vs 0.7s）；OpenAI 兼容端点传 `"thinking": {"type": "disabled"}` 即可关闭，输出质量不变。
3. **DeepSeek API 硬性要求**：关闭思考时 `temperature` 必须 = 0.2（否则报错）。
4. 现状：`config.llm_provider` 全局一个（clean/record 共用），默认 mimo。`openai_compat.py::complete()` 不支持 thinking 参数。
5. 基线耗时（MIMO v3，jobs 表实证）：59 段 clean 124.8s；56 段 clean 293.8s。

分支：`task/t-s1.5-deepseek-clean`（从 main 开）。提交消息：`[T-S1.5] type: 描述`。
**你不 merge、不 push、不打 tag**；自报写 `docs/handoffs/task-T-S1.5-self-report.md`。

## 钉死的决策

### 1. 清洗模型独立配置（不影响 record）

- `Settings` 新增两字段：`clean_llm_provider: str = "deepseek"`、`clean_llm_model: str = ""`（空则跟随 provider 默认，逻辑仿现有 `_resolve_llm_model`）。
- `services.py` 的 clean 阶段用 `clean_llm_provider`/`clean_llm_model` 构造 LLM；**record 阶段继续用 `llm_provider`（mimo）不动**——陛下 T-S0.6 既定决策，红线。
- `.env` 不加不改（默认值即生效）；`jobs` 表 clean 行的 `provider` 字段如实记 `deepseek`。
- 未来想切回：`.env` 一行 `CLEAN_LLM_PROVIDER=mimo`。

### 2. DeepseekLLM 支持关闭 thinking

- `openai_compat.py::complete()` 增加可选参数 `extra_body: dict | None = None`（合并进请求 body），MIMO/Qwen 路径不传不受影响。
- `DeepseekLLM` 覆写或构造时固定：请求 body 带 `"thinking": {"type": "disabled"}`、`temperature` 固定 0.2（**不受调用方 temperature 参数影响**，注释说明 API 硬约束）。
- 不改 `health_check`（max_tokens=5 已够）。

### 3. clean prompt 升 v4（吸收拼音推理链）

- 新建 `prompts/clean/v4.md`：在 v3 基础上，把「上下文纠错」规则升级为**拼音推理链**表述：
  「发现疑似识别错误时：先判断该词的读音，再列出同音/近音候选，按上下文选择最有把握的一个；读音差别过大或没把握时保留原文，宁可漏改不可改错。」
- 新增一条明确规则：「指代纠错：若全文语境明确指向某性别（如来访者谈妻子），相关代词他/她按语境纠正。」
- 其余规则与输出契约**原样保留**（角色判定/碎片合并/显式 [seq] 编号/JSON 输出/示例区）；示例区可补一个拼音推理链纠正的小示例（如 干喔→干呕 或 他→她）。
- `prompts.py` clean 注册表切到 v4；v1/v2/v3 文件不动；`prompt_version` 升 "v4"。

### 4. 测试

- 现有单测全过（fake LLM 路径不受影响）。
- 新增：`clean_llm_provider` 默认 deepseek 的单测（clean 调用走到 DeepseekLLM）；
- 新增：DeepseekLLM 请求 body 断言（含 `thinking.type=disabled`、`temperature=0.2`）——用 httpx MockTransport 或现有 fake 手法，**不真实调 API**。
- record 仍用 mimo 的断言（防回归）。

## 禁止清单

- 不改 record 阶段模型与 prompt（v2 不动）。
- 不整体引入 teamtee 框架代码（只蒸馏方法论进 prompt）。
- 不改前端、不改 API 契约、不引新依赖。
- 不真实调外部 API 跑测试；不碰 `.env`；不 merge/push/tag。

## 验收标准（大统领逐条实测）

1. pytest 全过 + ruff + 导入自检 + 前端构建（前端无改动也须构建确认）。
2. 请求 body 断言单测过（thinking disabled + temp 0.2）。
3. **真实端到端**（大统领执行）：陛下 56 段音频重跑，clean 走 deepseek-v4-flash，会话 done、重组正确、他/她纠错生效。
4. **耗时对比**（大统领执行）：同音频 clean 耗时对比基线 293.8s，记录在自报/台账。
5. 自报在 `docs/handoffs/task-T-S1.5-self-report.md`。

## 门禁

构建 → 测试 → 静态 → 前端构建；提交前 `git diff` 自查只含本卡范围。
