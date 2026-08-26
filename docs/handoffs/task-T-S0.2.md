# 任务卡 T-S0.2：Provider 接口 + 单一实现（S0 走骨架 · 第 2 张卡 · 架构基石）

## 背景与契约

项目「咨询记录助手」：录音 → ASR 转写（T/P 对话稿）→ 口语清理 → 客观咨询记录生成的 PWA。S0 走骨架增量进行中，T-S0.1 已交付后端骨架（FastAPI 包 `psyapp`，main 分支，见仓库根 `AGENTS.md`）。

本任务是 **D8 架构基石**：AI Provider 抽象层。方案文档 §4 钉死——ASR、LLM 均通过统一接口调用，实现可配置可替换。**接口在此一次定型**（后续增量不再改签名），但**只实现 P0 选定的各一个**：ASR=paraformer-v2（ADR-001 定夺），LLM=Qwen（DashScope）。第二个实现留到 S3 需要时再加，禁止提前做多实现。

仓库根：/home/houmo/meng/MengPsyAssit。先读 `AGENTS.md`（工作规则）再动手。

## 输入与环境事实（已核实）

- 后端包：`app/backend/src/psyapp/`（已可 `import psyapp.main`）；config.py 已有 `Settings.dashscope_api_key`（`repr=False`，仅定义未使用——本任务启用它）
- 依赖：.venv 已有 fastapi/sqlalchemy/dashscope 1.27.1/httpx；**装包用** `uv pip install -p .venv <pkg>`（系统 PEP 668 禁裸 pip）
- API Key：环境变量 `DASHSCOPE_API_KEY`（启动命令已注入，代码只读环境变量/Settings，绝不硬编码、绝不打印明文）
- **P0 已验证可用的参考实现（抄它的调用姿势，勿重新发明）**：
  - `tests/asr_eval/providers/paraformer.py`——paraformer-v2 完整调用链（oss 上传→提交异步任务→轮询→解析），P0 实测说话人分离 100% 全对
  - `tests/prompt_eval/run_prompt_eval.py`——Qwen compatible-mode 调用姿势，P0 实测通过
- **关键踩坑（P0 沉淀，必须遵守）**：paraformer 走**纯 HTTP 路径** + 请求头 `X-DashScope-OssResourceResolve: enable` 传 oss:// URL；**不要**用 dashscope SDK 传临时 URL（会 SERVER_ERROR/InvalidParameter.MalformedURL）
- 音频素材（勿改动）：`tests/audio/0{1,2,3}_*.wav`（16kHz mono，43.4/18.7/41.6s）

## 已钉死的路线决策

1. **接口签名**（对齐方案文档 §4，一次定型）：

```python
# psyapp/providers/base.py
class ASRProvider(ABC):
    name: str
    @abstractmethod
    def transcribe(self, audio_path: str, *, speaker_hint: int | None = 2) -> TranscriptResult: ...
    @abstractmethod
    def health_check(self) -> bool: ...

class LLMProvider(ABC):
    name: str
    @abstractmethod
    def complete(self, messages: list[dict], *, schema_hint: str | None = None, temperature: float = 0.3) -> str: ...
    @abstractmethod
    def health_check(self) -> bool: ...
```

2. **TranscriptResult**（dataclass，`psyapp/providers/base.py`）：`segments: list[Segment]`，Segment 含 `seq, speaker(str,"0"/"1"/…，说话人映射交给上层), text, start_ms, end_ms, confidence(float|None)` + `raw: dict`（原始 API 响应，供追溯）。**注意：provider 只吐说话人编号，"谁是 T" 的映射是上层业务，不在本层做。**
3. **工厂**：`psyapp/providers/__init__.py` 提供 `get_asr_provider(settings)` / `get_llm_provider(settings)`，按 `Settings` 字段选择实现（新增 Settings 字段：`asr_provider` 默认 `paraformer`、`llm_provider` 默认 `qwen`、`llm_model` 默认 `qwen-max`）；未知值抛清晰错误。
4. **实现类**：`psyapp/providers/paraformer.py`（DashScopeParaformer）、`psyapp/providers/qwen.py`（QwenLLM）。纯 HTTP 实现（urllib/httpx 二选一，.venv 已有 httpx），不依赖 dashscope SDK 做转写调用。
5. **paraformer 实现要点**（从参考实现移植）：
   - 本地文件先用 `.venv/bin/dashscope oss.upload --model paraformer-v2 --file <path>` 子进程上传，解析 `oss://...` URL；上传失败报清晰错误
   - 提交异步任务：POST `https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription`，headers 含 `X-DashScope-Async: enable` + `X-DashScope-OssResourceResolve: enable`，parameters 带说话人分离（照抄参考实现的参数）
   - 轮询 `GET /api/v1/tasks/{task_id}`（间隔 3s，总超时 15 分钟）；失败状态抛带 API 错误信息的异常
   - 解析 `output.results[].transcription_url` → 下载 → `transcripts[0].sentences[]` 组装 Segment（speaker 取 sentence 的 speaker_id 字符串化）
6. **Qwen 实现要点**：OpenAI 兼容端点 `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，model 取 `settings.llm_model`；`schema_hint` 非空时拼入 system 提示（简单实现即可）
7. **health_check**：ASR 用一次最小代价探测（如提交一个极短任务的 dry 检查或 key 有效性校验，自选简单可靠一种，注释说明策略）；LLM 用一次最小 completion（如 `messages=[{"role":"user","content":"ping"}]` max_tokens≤5）

## 要求

### 1. 代码：按上述 7 点实现（`psyapp/providers/` 包）

### 2. 单元测试（无网络，`app/backend/tests/test_providers.py`）
- 工厂：默认配置选出 paraformer+qwen；改 `asr_provider=xxx` 抛错
- paraformer 响应解析：手写一份仿真 transcription JSON fixture（结构照真实响应），断言解析出的 Segment 字段正确
- 至少 5 个用例，`pytest app/backend/tests -q` 全绿

### 3. 真实冒烟（有网络，`tests/provider_eval/smoke_providers.py`）
- 参数 `--asr` / `--llm` / 默认全跑；结果落盘 `tests/provider_eval/results/<时间戳>/`（每次请求的入参、响应原文、耗时）
- ASR 冒烟：对 `tests/audio/01_normal_dialogue.wav` 完整跑一遍 → 断言 ≥2 个说话人标签出现、段数 >10
- LLM 冒烟：qwen-max 一次中文 completion（如"用一句话说明什么是心理咨询记录"）→ 断言非空
- 结果文件**强制入库**（`git add -f`，这是证据）；写 `tests/provider_eval/README.md` 一句话说明用法

### 反面清单（违反即验收失败）

- ❌ 不实现第二个 provider（不做 qwen-asr、不做 deepseek-llm）
- ❌ 不写业务 API 端点（上传/转写/清理接口是 T-S0.3 的活）、不动 main 路由
- ❌ 不在 provider 层做"谁是 T"映射、不做文本清理等业务逻辑
- ❌ 不用 dashscope SDK 做转写调用（HTTP 直调，理由见踩坑）
- ❌ 不动 tests/audio/、tests/golden/、docs/、app/backend/prompts/
- ❌ 代码/日志/提交中出现 API key 明文
- ❌ 不合并 main、不打 tag

## 验收标准（编排方逐条实测）

1. 接口与工厂就位：`from psyapp.providers import get_asr_provider, get_llm_provider` 可用；签名与 §1 一致
2. 单测：`.venv/bin/python -m pytest app/backend/tests -q` 全过（含新增 ≥5 用例）
3. ruff：`.venv/bin/ruff check app/backend` 零错误
4. **真实冒烟（实测核心）**：`DASHSCOPE_API_KEY=*** .venv/bin/python tests/provider_eval/smoke_providers.py` 退出码 0；`results/<时间戳>/` 下有真实 API 往返记录（含 paraformer transcription_url 原文与 qwen 响应原文，非手填）；ASR 输出含 ≥2 个说话人
5. health_check 两个实现可调用（LLM 实测；ASR 按其策略实测）
6. 零密钥泄露：`git grep "sk-"` 在新代码中零命中（结果文件同样不得含 key）
7. git：分支 `task/t-s0.2-providers`，提交前缀 `[T-S0.2]`，冒烟结果 `git add -f` 入库（不合并）

## 技术约束

- 一切用 `.venv/bin/python`；装新依赖（若必需）用 `uv pip install -p .venv`，并在自报中说明理由
- SQLAlchemy/数据库本任务不碰
- 输出全部 UTF-8；provider 层日志不得打印请求 headers 的 Authorization 值
- 交付后在 `docs/handoffs/task-T-S0.2-self-report.md` 留自报（做了什么/跑了什么/结果如何）——自报不作数，编排方实测为准
