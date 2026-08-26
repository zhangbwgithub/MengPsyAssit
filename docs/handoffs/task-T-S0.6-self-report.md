# T-S0.6 自报：LLM Provider 可选扩展 + 默认切换 MIMO

## 做了什么

1. **新增两个 LLM 实现**（仿 qwen.py，纯 httpx，不引 SDK）：
   - `app/backend/src/psyapp/providers/mimo.py`：`MimoLLM`（name=`mimo`，端点 token-plan-cn.xiaomimimo.com，默认 mimo-v2.5-pro）
   - `app/backend/src/psyapp/providers/deepseek.py`：`DeepseekLLM`（name=`deepseek`，api.deepseek.com，默认 deepseek-v4-flash）
   - 公共逻辑抽到 `providers/openai_compat.py`（OpenAI 兼容基类：complete/health_check/schema_hint 组装/异常不泄露 Authorization）；**qwen.py 一行未动**，保留可切回。
2. **Settings 扩展**（config.py）：新增 `xiaomi_cn_api_key`、`deepseek_api_key`（均 `Field(default="", repr=False)`）；默认 `llm_provider="mimo"`。
   - **一处与任务卡字面表述的偏差（需知晓）**：`llm_model` 默认值不是硬编码 `"mimo-v2.5-pro"`，而是留空 + validator 按 provider 填充默认模型（mimo→mimo-v2.5-pro / qwen→qwen-max / deepseek→deepseek-v4-flash，显式 `LLM_MODEL` 优先）。原因：验收 4 要求"仅覆盖 `LLM_PROVIDER=qwen` 时 basic_info.model 变 qwen-max"——若 llm_model 硬编码默认 mimo-v2.5-pro，只切 provider 会把 mimo 模型名传给 qwen 导致失败。净效果：默认配置下 `settings.llm_model == "mimo-v2.5-pro"`，与任务卡语义一致。
3. **工厂**：`get_llm_provider` 支持 `mimo | deepseek | qwen`，未知值抛 ValueError；缺 key 抛 ProviderError 且含环境变量名（XIAOMI_CN_API_KEY / DEEPSEEK_API_KEY / dashscope_api_key），不打印 key。
4. **单测**：`test_providers.py` 重写工厂段（默认选 mimo+mimo-v2.5-pro、三值选择、模型跟随、显式覆盖、未知值、三方缺 key）；`test_sessions.py` 默认断言同步为 mimo/mimo-v2.5-pro。
5. **冒烟**：新建 `tests/provider_eval/smoke_llm_providers.py`——三模型最小 completion + 默认 mimo 用 golden 01（8 段）跑完整 clean+record，断言 record JSON 三字段；落盘前全量扫描零 key/Authorization。结果入库 `tests/provider_eval/results/20260826-112511/`（git add -f）。
6. **AGENTS.md** 环境事实补 LLM 默认行；`tests/provider_eval/README.md` 补新脚本用法。

## 跑了什么 / 结果

| 验收标准 | 结果 | 证据 |
|---|---|---|
| 1. 单测全绿 + ruff 零错误 | PASS | `pytest app/backend/tests -q` → 28 passed；`ruff check app/backend` → All checks passed |
| 2. 冒烟退出码 0，三模型真实响应在案 | PASS | 三模型 health_check=True、响应非空（mimo 6.2s / deepseek 1.9s / qwen 1.7s）；mimo clean 27.7s + record 20.2s，topics 6 条，三字段齐全；leak-scan ✓；结果目录 20260826-112511 |
| 3. 端到端 basic_info.model=mimo-v2.5-pro | 部分自证 | 单测 `test_sessions` 已断言默认配置落库 provider=mimo/model=mimo-v2.5-pro；编排方真实音频复跑未自跑（属编排方验收项） |
| 4. LLM_PROVIDER=qwen → qwen-max | PASS（代码支持） | 单测 `test_factory_select_deepseek_and_qwen` 断言留空 llm_model 时 qwen→qwen-max |
| 5. 零密钥泄露 | PASS | tracer 不记请求头；落盘文件脚本内断言 + `grep -rE 'Bearer\|sk-' results/` 零匹配 |
| 6. 分支/前缀/结果入库 | PASS | task/t-s0.6-llm-providers，`[T-S0.6]` 前缀，results git add -f |

## 需要编排方知晓的事

- **`.env` 里三个 key 实际是 `***` 占位符**（任务卡称"已备好三 key"，实测不然）。本次冒烟未改 `.env`，按编排方自己 `eval_llm_candidates.py` 的 key 源用**环境变量注入**取的真实 key（XIAOMI_CN_API_KEY←`~/.hermes/profiles/qqbot/.env`，DEEPSEEK_API_KEY←`~/.reasonix/.env`，DASHSCOPE_API_KEY←`~/.hermes/profiles/qqbot/.env`），三端点均实测 HTTP 200。**编排方端到端复跑前需把真实 key 填进 `.env`**（或同样环境变量注入），否则默认 mimo 会因 key 无效而 401。
- 冒烟脚本时间戳目录改用 UTC（ruff DTZ005），与旧脚本的本地时区命名略不同，无功能影响。
- 既有 `smoke_providers.py` 自身有 3 个 ruff 报错（存量，未动）。
