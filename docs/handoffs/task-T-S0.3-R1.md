# 任务卡 T-S0.3-R1：修正指令（第 1 次重试）—— schema 漂移导致真实上传 500

## 背景

你是 T-S0.3 的执行者。编排方（大统领）用**仓库根的既有 `data/app.db`**（T-S0.1 时代创建）真实冒烟时，`POST /sessions` 上传 500。你自测没炸，是因为冒烟脚本以 `app/backend/` 为 cwd 启动，相对路径 `sqlite:///data/app.db` 解析到全新目录，绕过了旧库。

## 具体错误（编排方实测）

```
sqlite3.OperationalError: table sessions has no column named cleaned_text
[SQL: INSERT INTO sessions (user_id, client_id, mode, status, started_at, duration_sec, audio_path, cleaned_text) VALUES (?, ?, ?, ?, ?, ?, ?, ?)]
[parameters: (1, None, 'in_person', 'uploading', ..., 'data/audio/77bffa61....wav', None)]
```

根因：本任务给 `sessions` 加了 `cleaned_text` 列，但 `Base.metadata.create_all()` 不会 ALTER 已存在的表。旧库缺列 → 插入即炸。这个洞后续每个增量加列都会踩，必须在本次修掉。

## 修正要求（只修这个，不扩范围）

### 1. `psyapp/db.py` 加轻量列补齐（SQLite 专用，替代 alembic 的 dev 期方案）

- `init_db()` 在 `create_all()` 之后增加一步 `_heal_missing_columns(engine)`：
  - 遍历 `Base.metadata.tables`，对每张表 `PRAGMA table_info(<表名>)` 取实际列集合
  - metadata 中有而实际缺的列 → `ALTER TABLE <t> ADD COLUMN <name> <type>`（类型用 SQLAlchemy 的 `compile(dialect=sqlite_dialect)` 渲染；新列一律 nullable、不带 default，简单可靠）
  - 幂等、无新列时零操作；日志记录补了哪些列（INFO 级）
  - 模块/函数注释写明：dev 期 SQLite 列补齐策略，正式迁移工具（alembic）留待需要时引入（任务卡禁 alembic 的约束不违反——这不是 alembic）

### 2. 单元测试（无网络，补在 `app/backend/tests/`）

- 构造旧 schema 场景：手工 `CREATE TABLE sessions(...)` 只含旧列（不含 cleaned_text），再调 `init_db()`，断言 `PRAGMA table_info` 出现 `cleaned_text` 且原列完好
- `pytest app/backend/tests -q` 全绿（原 23 用例不得破坏）

### 3. 真实冒烟重跑（关键变更：必须用仓库根的旧库）

- **先删掉你冒烟误建的 `app/backend/data/` 整个目录**（那是 cwd 相对路径的产物，不该存在）
- 冒烟启动服务时显式设置 `DATABASE_URL=sqlite:////home/houmo/meng/MengPsyAssit/data/app.db`（绝对路径，指向**旧库**——这正是要验证的场景：旧库被自动补齐后上传成功）
- 重跑 `tests/e2e/smoke_main_chain.py`（可加 `--database-url` 参数或直接环境变量，自选简单一种，脚本里注释说明），结果落新时间戳目录，`git add -f` 入库
- 冒烟脚本的 `run_server` 里 `cwd` 改为仓库根（消除相对路径歧义）

### 反面清单

- ❌ 不引 alembic；不改 providers/prompts/路由业务逻辑（除非与修复直接相关）
- ❌ 不删仓库根的 `data/`（那是合法运行时目录；只删误建的 `app/backend/data/`）
- ❌ 不合并 main、不打 tag
- ❌ 密钥零泄露照旧

## 验收标准（编排方实测）

1. `pytest app/backend/tests -q` 全绿（含新增旧库补齐用例）；ruff 零错误
2. 编排方用仓库根旧库直接起服务 + 真实上传合成音频 → 状态走到 done（**这是上次失败的原场景，必须过**）
3. 旧库 `sessions` 表被补上 `cleaned_text` 列，原有数据行不丢（dev 用户行还在）
4. `app/backend/data/` 目录已删除
5. 新冒烟结果入库，提交前缀 `[T-S0.3]`，消息含 "fix: schema 列补齐" 字样
6. 自报附：修复前后旧库实测对比（补列前后各一次 `PRAGMA table_info` 输出）

## 技术约束

- 分支继续在 `task/t-s0.3-main-chain` 上追加提交
- `.venv/bin/python`；启动前缀注入 `DASHSCOPE_API_KEY`（同前）
- 自报不作数，编排方实测为准
