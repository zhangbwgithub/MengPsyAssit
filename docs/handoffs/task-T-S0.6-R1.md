# 任务卡 T-S0.6-R1：修复 paraformer OSS 上传子进程缺 DASHSCOPE_API_KEY（验收引爆）

## 背景

大统领验收 T-S0.6 端到端复跑时引爆一个产品级漏洞（S0.2 埋下）：

```
psyapp.providers.base.ProviderError: dashscope oss.upload 失败（rc=1）:
Error: Please set your DashScope API key as environment variable DASHSCOPE_API_KEY or pass it as argument by -k/--api-key
```

**病灶**：`app/backend/src/psyapp/providers/paraformer.py` 的 `_upload_oss` 用 `subprocess.run([cli, "oss.upload", ...])` 调 dashscope CLI，CLI 依赖环境变量 `DASHSCOPE_API_KEY`；但 pydantic-settings 只把 key 读进 `Settings` 对象，不会导出到子进程环境。构造函数已有 `self._api_key`，只是没传给子进程。之前会话能跑全因启动 shell 恰好导出了该环境变量——干净启动（如 `systemd` / 裸 `uvicorn`）必挂。

## 要求

### 1. 修复（最小化）
- `_upload_oss`：`subprocess.run(..., env={**os.environ, "DASHSCOPE_API_KEY": self._api_key}, ...)`
- 不用 `-k/--api-key` 命令行传参（进程列表可见，密钥泄露面更大）
- 不改其他逻辑

### 2. 单测（不跑真实 CLI）
- `tests/test_providers.py` 增用例：mock `subprocess.run`，断言调用时传入的 `env` 含 `DASHSCOPE_API_KEY` 且值等于构造时传入的 key（mock 里用假 key 即可）
- 原有 28 项单测全绿不回归

### 3. 自查
- ruff 零错误
- 零密钥泄露：代码/测试无真实 key 明文

### 反面清单
- ❌ 不碰 `.env`（编排方管理）
- ❌ 不改 LLM 侧（mimo/deepseek/qwen）
- ❌ 不改接口签名、不合并、不打 tag

## 验收标准（编排方实测）

1. 单测全绿 + ruff 零错误
2. **干净环境端到端**：不导出任何 key 环境变量，仅凭项目 `.env`（pydantic-settings 读取）起服务，上传 `tests/audio/01_normal_dialogue.wav` 走完全链路：转写成功 + 记录落库 `basic_info.model == mimo-v2.5-pro`
3. git：分支 `task/t-s0.6-llm-providers`（继续，勿新开），提交前缀 `[T-S0.6-R1]`

## 交付后
`docs/handoffs/task-T-S0.6-R1-self-report.md` 一句话自报。
