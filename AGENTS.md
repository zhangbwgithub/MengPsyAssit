# AGENTS.md — 咨询记录助手（MengPsyAssit）工作规则

项目：录音 → ASR 转写（T=咨询师 / P=来访者对话稿）→ 口语清理 → 客观咨询记录生成的 PWA。
当前阶段：S0 走骨架（最薄端到端主链路）。

## 角色分工
- 大统领：编排任务卡、逐条验收、合 main、打 tag。
- Reasonix（本 agent）：编码 + 自测 + 自报；不 merge、不 push main、不打 tag。
- 陛下：产品与范围决策；范围/方向变更须陛下拍板。

## 分支与提交
- 每张任务卡开分支：`task/<ID>-<slug>`（如 `task/t-s0.1-backend-skeleton`）。
- 提交消息：`[T-xx.x] type: 描述`（type ∈ feat/fix/docs/chore/test/refactor）。
- main 只进大统领验收过的代码；提交前自查 diff：只含本卡范围，无残留文件。

## 环境事实
- Python：`.venv/bin/python`（3.11.15）；系统 PEP 668，禁止裸 pip 装系统包。
- uv：`/home/houmo/.local/bin/uv`；Reasonix 会话命令加前缀 `HOME=/home/houmo`。
- 常用命令：
  - 装后端：`uv pip install -p .venv -e "app/backend[dev]"`
  - 测试：`.venv/bin/python -m pytest app/backend/tests -q`
  - 静态检查：`.venv/bin/ruff check app/backend`
  - 启动：`.venv/bin/python -m uvicorn psyapp.main:app --port 8660`
  - 导入自检：`.venv/bin/python -c "import psyapp.main"`
- LLM：默认 mimo（mimo-v2.5-pro，T-S0.6 陛下拍板），可选 qwen / deepseek——`.env` 里 `LLM_PROVIDER` 切换；`llm_model` 留空自动跟随 provider 默认模型。三 key：XIAOMI_CN_API_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY。

## 红线清单
- `.env` / `.env.*` / `*_api_key*` 永不进 git；不新建 `.env`（由编排方管理）。
- API key 不进代码、不进日志、不进自报；出现 `sk-` 明文即验收失败。
- 测试只用合成音频（`tests/audio/`），不碰真实咨询数据。
- 禁止镀金超范围；不引 alembic/Celery/Redis/aiosqlite 等 S0 不需要的组件。
- 勿动：`tests/audio/`、`tests/golden/`、`docs/`（任务卡允许的自报除外）、`app/backend/prompts/`。
- 运行时数据走 `data/`（已 gitignore）；不提交音频/数据库文件。

## 门禁与证据制摘要
- 每卡交付前按序跑：构建（uv install + import）→ 测试（pytest）→ 审查（ruff，必要时 review skill）。
- 自报逐条对照验收标准报 `PASS` / `FAIL` / `NOT RUN`，并附实际命令与结果。
- 自报不作数：以大统领实测为准。

## 文档归位
- ADR → `docs/adr/`；进度 → `docs/progress/`；交接 → `docs/handoffs/CURRENT.md`。
- 每卡在任务卡同目录留一句话自报（做了什么 / 跑了什么命令 / 结果如何）。

## 架构速览
- 后端包：`app/backend/src/psyapp/`
  - `main.py`：create_app 工厂 + 模块级 app；`GET /health`
  - `config.py`：pydantic-settings（`.env` 缺失用默认值，data_dir 自动创建）
  - `models.py`：7 张表（users/clients/sessions/segments/records/themes/jobs），业务表带 user_id 隔离列
  - `db.py`：SQLAlchemy 2.0 engine/session + `init_db()`（create_all + dev 播种）
  - `response.py`：`{ok:true,data}` / `{ok:false,error:{code,message}}` + 全局异常处理
  - `logging_conf.py`：stdout 统一格式 + 密钥掩码过滤
  - `enums.py`：业务枚举字符串常量
- 测试：`app/backend/tests/`（临时 SQLite + TestClient）

## Notes
- （留空，后续快速补充）
