# 任务卡 T-S0.3：最简主链路 API（S0 走骨架 · 第 3 张卡）

## 背景与契约

项目「咨询记录助手」：录音 → ASR 转写（T=咨询师/P=来访者）→ 口语清理 → 客观咨询记录生成。S0 走骨架进行中：T-S0.1 交付后端骨架（`psyapp` 包 + 7 表数据模型 + 统一响应），T-S0.2 交付 Provider 抽象层（`psyapp.providers`：paraformer-v2 + qwen-max，均已真实冒烟通过），全部在 main 分支。

本任务：**把最薄端到端主链路接通**——上传音频文件 → 后台转写 → segments 落库 → 最简清理 → 最简记录生成 → 查询返回。这是 S0 的核心卡，做完它前端（T-S0.4）就有东西可展示。

仓库根：/home/houmo/meng/MengPsyAssit。先读 `AGENTS.md` 与 `docs/handoffs/CURRENT.md` 再动手。

## 输入与环境事实（已核实）

- 后端骨架：`app/backend/src/psyapp/`（main.py create_app 工厂、config.py Settings、db.py、models.py 7 表、response.py 统一响应 `{ok, data|error}` + ApiError、enums.py 状态常量、logging_conf.py）
- Provider 层（勿改接口）：
  - `from psyapp.providers import get_asr_provider, get_llm_provider`；`get_settings()` 取 Settings（读环境变量 `DASHSCOPE_API_KEY`）
  - ASR：`transcribe(audio_path, speaker_hint=2) -> TranscriptResult`，`.segments[]`（Segment: seq, speaker 编号字符串 "0"/"1", text, start_ms, end_ms, confidence）
  - LLM：`complete(messages, schema_hint=None, temperature=0.3) -> str`
- Prompt 模板（勿改动，直连使用）：
  - `app/backend/prompts/clean/v1.md`：占位符 `{{transcript}}`，输入输出均为 `T: 文本`/`P: 文本` 逐行格式
  - `app/backend/prompts/record/v1.md`：占位符 `{{cleaned_transcript}}`，输出纯 JSON（summary / counselor_work / client_reported_topics）
- 测试音频：`tests/audio/01_normal_dialogue.wav`（43.4s，双音色，冒烟用）
- API Key：环境变量 `DASHSCOPE_API_KEY`（启动命令已注入）；装包用 `uv pip install -p .venv`
- 端口约定：后端开发端口 8660

## 已钉死的路线决策（不给二次选择）

1. **说话人映射（S0 最简策略）**：S0 不做点选映射（S2 的活）。策略：上传接口可选参数 `speaker_zero`（`"T"|"P"`，默认 `"T"`）——ASR 的 speaker 编号 "0" 映射为该值，"1" 映射为另一个；映射结果直接写进 segments.speaker。
2. **后台执行**：FastAPI `BackgroundTasks` 起一个任务函数串行跑「转写→清理→记录」（S0 单机单会话量，不引队列中间件——禁镀金）。任务状态进 `jobs` 表（type=transcribe/clean/record 各一行，或单行串联，二选一，注释说明）。
3. **会话状态机最小版**：`uploading`（上传中，创建即写）→ `transcribing`（后台任务开始）→ `done` / `failed`。失败时 jobs.error 记原因，会话可重新提交（新端点或复用，自选简单一种）。
4. **清理与记录的"最简"**：一次整体调用（不做逐段分批——加固是 S3 的活）；LLM 返回解析失败 → 重试 1 次，仍失败标 failed 并记错误。
5. **路由设计**（RESTful，统一响应封装）：
   - `POST /sessions`（multipart：file + 可选 speaker_zero）：校验类型/大小（≤200MB）→ 存 `data/audio/<uuid4 随机名>` → 建 sessions 行（user_id=dev_user_id, mode=in_person）→ 起后台任务 → 返回 `{session_id, status}`
   - `GET /sessions/{id}`：会话状态 + segments（按 seq）+ cleaned_text（若有）+ record（若有）
   - `GET /sessions`：会话列表（id/status/时间，dev 用户）
   - 参数校验失败/404/超限 一律走统一错误结构
6. **文件校验**：只收 `.wav/.m4a/.mp3/.opus/.flac`；扩展名+大小双校验，超限 413/400 清晰错误。
7. **prompt 加载**：模板文件路径可配置（默认 `app/backend/prompts`，相对仓库根解析），替换占位符用简单字符串替换。
8. **可追溯**：records.basic_info 存 `{provider, model, prompt_version:"v1", session_id}`（方案 §6.2 要求）。

## 要求

### 1. 代码实现（`psyapp/` 内，建议新增 `routes/`、`services/` 模块，main.py 挂路由）

### 2. 单元测试（无网络，`app/backend/tests/`）
- 用 monkeypatch/fake provider 打桩，跑通：上传→状态流转→segments 落库→清理文本→记录 JSON 解析落库
- 覆盖：上传非法扩展名拒绝；超大小拒绝；404 会话；LLM 返回坏 JSON 时的重试与 failed 状态
- `pytest app/backend/tests -q` 全绿（原有 13 用例不得破坏）

### 3. 真实冒烟（有网络，`tests/e2e/smoke_main_chain.sh` 或 .py）
- 启动服务（可用 8661 端口避开占用）→ `curl` 上传 `tests/audio/01_normal_dialogue.wav` → 轮询 `GET /sessions/{id}` 至 done（超时 10 分钟）→ 断言：状态 done、segments ≥10 且含 T 与 P 两种 speaker、cleaned_text 非空、record 含 summary/counselor_work
- 冒烟全程输出落盘 `tests/e2e/results/<时间戳>/`（响应原文），**强制入库**（`git add -f`）

### 反面清单（违反即验收失败）

- ❌ 不改 providers 层接口与实现（有问题报告，不擅改）；不动 prompts/ 模板
- ❌ 不做前端、不做分片上传、不做编辑/映射/撤销/搜索/登录（后续增量的活）
- ❌ 不引 Celery/Redis/任务队列中间件；不引 alembic
- ❌ 不清理/覆盖 `data/` 已有内容之外的结构；音频文件必须随机文件名（不可枚举）
- ❌ 代码/日志/提交/冒烟结果中出现 API key 明文
- ❌ 不合并 main、不打 tag

## 验收标准（编排方逐条实测）

1. 单测全绿：`pytest app/backend/tests -q` ≥19 用例（原 13 + 新增 ≥6）
2. ruff：`ruff check app/backend` 零错误
3. **真实端到端（核心）**：冒烟脚本退出码 0；`tests/e2e/results/` 下有真实往返记录；`GET /sessions/{id}` 最终返回 `status=done`、segments 含 T/P 双说话人、cleaned_text 非空、record 三字段齐全（编排方亲自跑一遍，不信自报）
4. 失败路径实测：上传 `.txt` 文件返回统一错误结构（非 500）
5. 会话状态机：上传后 `transcribing`，完成后 `done`（轮询过程可见）
6. 音频文件落盘为随机名（非原始文件名）
7. 零密钥泄露：`git grep "sk-"` 新增代码零命中；冒烟结果文件无 key/Authorization
8. git：分支 `task/t-s0.3-main-chain`，提交前缀 `[T-S0.3]`，冒烟结果 `git add -f`（不合并）

## 技术约束

- 一切用 `.venv/bin/python`；启动命令前缀注入 `DASHSCOPE_API_KEY`（同 T-S0.2 姿势）
- 输出全部 UTF-8；日志不打印 Authorization 头
- 长轮询/转写任务注意：paraformer 43s 音频实测约 1-2 分钟完成，冒烟超时要给足
- 交付后在 `docs/handoffs/task-T-S0.3-self-report.md` 留自报——自报不作数，编排方实测为准
