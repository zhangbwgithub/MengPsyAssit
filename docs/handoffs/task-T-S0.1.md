# 任务卡 T-S0.1：治理基线 + 后端骨架（S0 走骨架 · 第 1 张卡）

## 背景与契约

项目「咨询记录助手」：录音 → ASR 转写（T=咨询师/P=来访者对话稿）→ 口语清理 → 客观咨询记录生成的 PWA 工具。P0 技术验证已全部完成（ASR 选型 paraformer-v2、clean/record prompt 骨架 v1 已实测）。现在进入 **S0 走骨架**增量：最薄端到端主链路（上传音频→转写→清理→记录生成→单页展示）。本任务是 S0 第一张卡：**打地基**——仓库治理规则 + FastAPI 后端骨架 + 数据模型基线。

仓库根：/home/houmo/meng/MengPsyAssit（所有相对路径以此为根）。

**本任务不接任何 AI Provider、不写业务 API、不做前端**——只立骨架。骨架立得直，后续 T-S0.2~T-S0.5 才能快。

## 输入与环境事实（已核实，勿重复试错）

- Python：`.venv/bin/python`（3.11.15）。依赖管理用 **uv**（`/home/houmo/.local/bin/uv`），装包命令：`uv pip install -p .venv <pkg>`（系统 PEP 668，禁止裸 pip 装系统）。
- `.venv` 现状：只有 dashscope 1.27.1 等 P0 依赖；**没有** fastapi/uvicorn/sqlalchemy/pytest/ruff——需要你装。
- `.gitignore` 已有规则：`.env` / `data/` / `*.wav`（`tests/audio/*.wav` 已例外放行）——先读一遍再动它，只增补不破坏。
- prompts 已存在（P0 产出，勿动）：`app/backend/prompts/{clean,record}/v1.md`。
- `app/backend/` 目前只有 `.gitkeep`、`README.md`、`prompts/`——后端代码从零建。
- git 身份仓库已配好，直接提交即可。分支模型见下文要求。

## 已钉死的路线决策（不给二次选择）

1. **后端栈**：FastAPI + SQLAlchemy 2.0（typed/Mapped 风格）+ SQLite（stdlib sqlite3，S0 阶段不用 FTS5/不用 aiosqlite）。
2. **包布局**：`app/backend/pyproject.toml` + src 布局，包名 `psyapp`，源码在 `app/backend/src/psyapp/`。可编辑安装进项目 .venv：`uv pip install -p .venv -e app/backend`。
3. **数据模型从第一天带 user_id 列**（硬要求）：S0 是 dev 单用户模式不做登录，但表结构必须预留多用户隔离，S4 加认证时零迁移。
4. **配置**：pydantic-settings 从 `.env` 读（文件不存在时用默认值，不得崩溃）。
5. **分支**：本任务在 `task/t-s0.1-backend-skeleton` 分支开发，验收后由编排方合 main——你**不要**动 main。

## 要求

### 1. 依赖与工程文件

- `app/backend/pyproject.toml`：包元数据 + 依赖（fastapi、uvicorn[standard]、sqlalchemy>=2、pydantic-settings）+ dev 依赖组（pytest、httpx、ruff）+ ruff/pytest 配置（ruff line-length 100；pytest testpaths 指向 `app/backend/tests`）。
- 装包：`uv pip install -p .venv -e "app/backend[dev]"`（若 uv 版本语法不支持 dev extra 的该写法，可分两次装，结果等价即可）。

### 2. FastAPI 骨架（`app/backend/src/psyapp/`）

- `main.py`：create_app 工厂 + 模块级 `app`。路由 `GET /health` → `{"status":"ok","app":"psy-backend","env":"<APP_ENV>"}`；startup 时初始化数据库（create_all）+ dev 模式播种默认用户（见 3）。
- `config.py`：pydantic-settings `Settings`，字段至少：`app_env`（默认 dev）、`database_url`（默认 `sqlite:///data/app.db`）、`data_dir`（默认 `data`）、`dev_user_id`（默认 1）、`dashscope_api_key`（默认空串，**仅定义，本任务不使用、不打印**）。自动确保 data_dir 存在。
- `response.py`：统一响应封装。成功：`{"ok":true,"data":...}`；失败：`{"ok":false,"error":{"code","message"}}`。提供业务异常类（如 `ApiError(code, message, http_status)`）+ 全局 exception handler（ApiError / RequestValidationError / 未知异常兜底 500，日志记录 traceback）。
- `logging_conf.py`：统一日志格式（时间/级别/模块），stdout 输出，日志中**永不**出现 api key（settings 的 key 字段 repr 掩码或日志侧过滤均可，选简单可靠的一种）。
- `db.py`：SQLAlchemy 2.0 engine/session（sessionmaker）+ `init_db()`（create_all + dev 播种）。

### 3. 数据模型 `models.py`（按方案文档 §5 定表，SQLAlchemy 2.0 Mapped 风格）

表清单（字段对齐方案文档，不增不减核心字段）：

| 表 | 关键字段 |
|----|----------|
| users | id, username(UK), password_hash |
| clients | id, **user_id** FK, code（UK(user_id,code)）, note, status(active\|disabled) |
| sessions | id, **user_id** FK, client_id FK(nullable), mode(in_person\|meeting), status(recording\|uploading\|transcribing\|done\|failed), started_at, duration_sec, audio_path |
| segments | id, session_id FK, **user_id** FK, seq, speaker(T\|P\|U), source(asr\|user), content, start_ms, end_ms, confidence |
| records | id, **user_id** FK, client_id FK(nullable), session_id FK(nullable), record_time, status(draft\|saved), basic_info(json), summary, therapist_work, notes |
| themes | id, record_id FK, type(dream\|growth\|trauma), content |
| jobs | id, type(transcribe\|clean\|record\|themes), session_id FK, provider, status(pending\|running\|done\|failed), error |

- dev 播种：`init_db()` 在 `app_env=dev` 且 users 为空时插入 `id=dev_user_id, username="dev"` 用户（幂等）。
- 枚举值用字符串常量模块（如 `enums.py`）集中定义，不散落魔法字符串。

### 4. 测试基线 `app/backend/tests/`

- `conftest.py`：fixture 提供临时 SQLite（tmp_path）+ TestClient。
- 至少 3 个测试：① `/health` 返回 200 且 `status=ok`；② init_db 后 7 张表全部存在、且 sessions/segments/records/clients 带 user_id 列（反射检查）；③ 404 路由返回统一错误结构（`ok=false` + error.code）。
- `uv run`/`.venv/bin/python -m pytest app/backend/tests -q` 全绿。

### 5. 治理基线 `AGENTS.md`（仓库根）

给后续所有 agent 会话的工作规则（精炼、可执行，≤120 行）：
- 角色分工（大统领编排验收 / Reasonix 编码 / 陛下决策）；
- 分支与提交规范（`task/<ID>-<slug>`；提交消息 `[T-xx.x] type: 描述`；main 只进验收过的代码）；
- 环境事实（.venv + uv 装包姿势、reasonix 需 `HOME=/home/houmo` 前缀）；
- 红线清单（.env 永不进 git、key 不进日志、测试只用合成音频不碰真实咨询数据、禁止镀金超范围）；
- 门禁与证据制摘要（构建→测试→审查；每条验收报 PASS/FAIL/NOT RUN）；
- 文档归位（ADR→docs/adr/、进度→docs/progress/、交接→docs/handoffs/CURRENT.md）。

### 6. .gitignore 增补

补 `app/backend/` 工程产物规则（如 `__pycache__/`、`*.egg-info/`、`.pytest_cache/`、`.ruff_cache/`、reasonix 运行日志目录 `.reasonix-runs/`）——先读现有内容，已有的不重复加。

### 反面清单（违反即验收失败）

- ❌ 不实现 ASR/LLM Provider（T-S0.2 的活）、不写上传/转写等业务 API（T-S0.3 的活）、不碰前端（T-S0.4）
- ❌ 不做登录/认证/JWT（S4 的活）；dev 单用户模式即可
- ❌ 不动 `tests/audio/`、`tests/golden/`、`docs/`（AGENTS.md 除外）、`app/backend/prompts/`
- ❌ 不硬编码/打印任何 API key；不新建 `.env` 文件（该文件由编排方管理）
- ❌ 不引入 alembic/Celery/Redis/aiosqlite 等 S0 不需要的组件
- ❌ 不合并到 main、不打 tag（编排方操作）

## 验收标准（编排方逐条实测）

1. `uv pip install -p .venv -e app/backend`（或等价）成功；`.venv/bin/python -c "import psyapp.main"` 无错
2. `.venv/bin/python -m uvicorn psyapp.main:app --port 8660` 可启动；`curl /health` 返回 200 + `{"status":"ok",...}`；错误路由返回统一 `{ok:false}` 结构
3. `.venv/bin/python -m pytest app/backend/tests -q` 全过（≥3 用例）
4. `.venv/bin/ruff check app/backend` 零错误
5. 7 张表结构符合 §3 表格（抽查 sessions/segments/records 有 user_id 列）
6. `AGENTS.md` 存在于仓库根且覆盖上述 6 个板块
7. 全程零密钥泄露（代码与日志中无 sk- 明文）
8. git：分支 `task/t-s0.1-backend-skeleton`，提交消息前缀 `[T-S0.1]`，代码+AGENTS.md 全部提交（不合并）

## 技术约束

- 一切用 `.venv/bin/python` / `.venv/bin/<tool>`；装包用 `uv pip install -p .venv`
- 输出全部 UTF-8；SQLite 文件路径走 `data/`（已 gitignore）
- SQLAlchemy 2.0 typed 风格（DeclarativeBase + Mapped[]），不用旧式 Column 声明
- 交付后在任务卡同目录留一句话自报（做了什么、跑了什么命令、结果如何）——但记住：自报不作数，编排方实测为准
