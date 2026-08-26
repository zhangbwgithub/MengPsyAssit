# 任务卡 T-S0.6：LLM Provider 可选扩展 + 默认切换 MIMO（陛下拍板，提前自 S3）

## 背景与契约

项目「咨询记录助手」：后端已有 Provider 抽象层（`psyapp/providers/`：`ASRProvider`/`LLMProvider` 接口 + paraformer ASR + qwen LLM）。陛下拍板：**LLM 要可选，默认从 qwen-max 换成 MIMO-v2.5-pro**（成本更低）。原计划第二实现留到 S3，现提前。

编排方已用 04 号音频真实对话稿（59 段）+ 诱导样本实测三个候选，结论钉死：

| 候选 | 标签保真（59段） | 诱导样本安全 | record JSON | 备注 |
|------|------|------|------|------|
| **mimo-v2.5-pro** | **59/59 零错位** | ✅ 全"自述"句式 | ✅ 合法 | **新默认** |
| deepseek-v4-flash | 58/59（首段 T/P 错位） | ✅ | ✅ 合法 | 备选，保真瑕疵已知 |
| qwen-max | 基线（已通过验收） | ✅ | ✅ | 保留 |

仓库根：/home/houmo/meng/MengPsyAssit。先读 `AGENTS.md` 与 `app/backend/src/psyapp/providers/`（qwen.py 是参考实现）。

## 输入与环境事实（已核实）

- 现有 `QwenLLM`（`providers/qwen.py`）：DashScope compatible-mode，`complete(messages, schema_hint, temperature)` + `health_check()`；工厂 `get_llm_provider(settings)` 按 `settings.llm_provider` 选择，未知值抛 ValueError
- 项目 `.env` **已备好**（编排方管理，含 `DASHSCOPE_API_KEY` / `XIAOMI_CN_API_KEY` / `DEEPSEEK_API_KEY` 三 key）——pydantic-settings 会自动读；**你不新建、不修改 .env**
- MIMO 端点（实测连通）：`https://token-plan-cn.xiaomimimo.com/v1/chat/completions`，OpenAI 兼容（Bearer 鉴权），model=`mimo-v2.5-pro`，temperature 生效，返回结构同 OpenAI（choices[0].message.content + usage）
- DeepSeek 端点：`https://api.deepseek.com/v1/chat/completions`，OpenAI 兼容，model=`deepseek-v4-flash`（注意：该模型带 reasoning，输出较慢，clean 59 段实测约 2 分钟，属正常）
- 测试/运行：`.venv/bin/python`；装包 `uv pip install -p .venv`

## 已钉死的路线决策

1. **新增两个实现**（结构仿 `qwen.py`，纯 httpx，不引 SDK）：
   - `providers/mimo.py`：`MimoLLM`，端点如上，name=`mimo`
   - `providers/deepseek.py`：`DeepseekLLM`，端点如上，name=`deepseek`
2. **Settings 扩展**（`config.py`）：
   - 新增 `xiaomi_cn_api_key`、`deepseek_api_key`（均 `Field(default="", repr=False)`）
   - **默认值改为** `llm_provider="mimo"`、`llm_model="mimo-v2.5-pro"`
3. **工厂**：`get_llm_provider` 支持 `mimo | deepseek | qwen` 三值；mimo 无 key / deepseek 无 key / qwen 无 dashscope key 时抛清晰 `ProviderError`（含缺哪个环境变量名，不打印 key）
4. **health_check**：各实现用最小 completion（同 qwen 现有策略，max_tokens 小）
5. **不改** `ASRProvider` 与 paraformer 实现、不改接口签名、不改 prompts/、不改业务路由（routes/services 继续只认 `LLMProvider` 接口——这正是抽象层的目的）

## 要求

### 1. 代码实现（上述 5 点）

### 2. 单元测试（无网络，`tests/test_providers.py` 扩展）
- 工厂默认选出 `mimo` + `mimo-v2.5-pro`；`llm_provider=deepseek` / `qwen` 各选出对应实现；未知值抛错；mimo 无 key 时抛 ProviderError 且错误信息含 `XIAOMI_CN_API_KEY` 字样
- 原有单测全绿不回归

### 3. 真实冒烟（`tests/provider_eval/smoke_llm_providers.py`，扩展或新建，自说明）
- 对三个 LLM 各跑一次最小真实 completion（如"用一句话说明什么是心理咨询记录"）
- 再对**默认 mimo** 跑一次完整 clean+record 链路验证：用 `tests/golden/01_normal_dialogue.json` 构造对话稿 → clean prompt → record prompt → 断言 record JSON 三字段齐全
- 全部往返落盘 `tests/provider_eval/results/<时间戳>/` 并 `git add -f` 入库；**结果中不得出现任何 key/Authorization**

### 4. 更新 `AGENTS.md` 环境事实一节
- 补一行：LLM 默认 mimo-v2.5-pro，可选 qwen/deepseek（.env 切换）

### 反面清单

- ❌ 不新建/不修改 `.env`（编排方管理）；不打印/不落盘任何 key
- ❌ 不改 ASR 侧、不改接口签名、不改业务路由逻辑、不改 prompts 模板
- ❌ 不删 qwen 实现（保留可切回）
- ❌ 不合并、不打 tag

## 验收标准（编排方逐条实测）

1. 单测全绿（含新增工厂/缺 key 用例）；ruff 零错误
2. 冒烟脚本退出码 0：三模型真实响应在案（含 mimo 完整 clean+record 链路）
3. **编排方端到端复跑**：默认配置（不传任何环境变量覆盖）起服务，上传 `tests/audio/01_normal_dialogue.wav` 走完全链路 → 记录落库的 `basic_info.model` 必须是 `mimo-v2.5-pro`（不是 qwen-max）
4. 切换验证：`.env` 注释切换或环境变量覆盖 `LLM_PROVIDER=qwen` 时，`basic_info.model` 变 `qwen-max`（编排方自测，你保证代码支持）
5. 零密钥泄露：代码/结果/日志无 key 明文
6. git：分支 `task/t-s0.6-llm-providers`，提交前缀 `[T-S0.6]`，冒烟结果入库

## 技术约束

- `.venv/bin/python`；MIMO/DeepSeek 调用超时给足（180s，reasoning 模型慢）
- 日志不打印 Authorization
- 交付后 `docs/handoffs/task-T-S0.6-self-report.md` 自报——自报不作数，编排方实测为准
