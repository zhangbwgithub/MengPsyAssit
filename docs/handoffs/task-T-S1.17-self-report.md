# T-S1.17 自报：来访者档案 API（FB-014 客户需求①，批次 A 后端）

## 做了什么

- `app/backend/src/psyapp/models.py`：`Client` 表加 8 列（全部可空，name 业务必填由 API 层校验）：
  `name`(String64) / `gender` / `age` / `phone` / `emergency_contact` / `emergency_phone` / `start_date`(Date) / `session_count_manual`。
  走既有 `_heal_missing_columns` 列自愈，不动旧数据；`code` 保留作内部代号。
- `app/backend/src/psyapp/routes.py`：
  - `GET /clients`：active 优先 + start_date 降序（无日期按 id 降序兜底）；每条含档案全字段 + `session_count_auto`（名下所有状态会话数）+ `session_count`（手工值优先，否则自动值）。
  - `POST /clients`：name 必填/空名/同用户重名 → 422；未传 code 时回填 `C+client_id`；start_date 非 YYYY-MM-DD → 422；非法 status → 422。
  - `PATCH /clients/{id}`：`model_fields_set` 口径只更新传入字段；重名 422；非法 status 422；不存在 404。
  - `DELETE /clients/{id}`：硬删行，名下会话 `client_id` 置 null，返回 `{deleted, affected_sessions}`。
  - `PATCH /sessions/{id}`：`SessionPatch` 加 `client_id`（显式传才更新；非空校验存在且同用户否则 404；显式 null 解绑），返回值加 `client_id`。
  - `GET /sessions`（列表）/ `GET /sessions/{id}`（详情）/ `GET /export/sessions`（导出）：富化 `client_id`、`client_name`（无则 null）。
- `app/backend/tests/test_clients.py`（新增 4 个测试）：CRUD 全链 + 自动 code 回填 + session_count 手工优先口径 + 重名/非法 status/非法 start_date/age 非整数 422；SessionPatch 挂/解绑/404；列表/详情/导出带 client_name；旧 clients 表列自愈读写。

## 跑了什么命令

```bash
HOME=/home/houmo .venv/bin/python -m pytest app/backend/tests -q
```
结果：`86 passed in 23.80s`（82 基线 + 新增 4）。

```bash
HOME=/home/houmo .venv/bin/ruff check app/backend
```
结果：`All checks passed!`。

```bash
HOME=/home/houmo .venv/bin/python -c "import psyapp.main"
```
结果：无异常（退出码 0）。

## 验收对照

1. pytest 全过（86 passed）—— PASS。
2. ruff All checks passed —— PASS。
3. import psyapp.main 无异常 —— PASS。
4. `git diff` 只含 `app/backend/src/psyapp/models.py`、`app/backend/src/psyapp/routes.py`、`app/backend/tests/test_clients.py`（新增）+ 本自报；未改前端/prompt/`tests/audio/`/`tests/golden/`；未引新依赖 —— PASS（工作区另有编排方未提交的 `tests/audio/*` 文件，不属于本卡，未纳入提交）。
5. 完工提交：分支 `task/t-s1.17-clients-api`（checkout 时已在该分支），commit 前缀 `[T-S1.17]`，本自报一并提交 —— PASS。
