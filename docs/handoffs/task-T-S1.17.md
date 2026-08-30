# Task T-S1.17: 来访者档案 API（FB-014 客户需求①，批次 A 后端）

## 背景

客户新需求（/home/houmo/meng/MengPRD.md，FB-014 解读）：来访档案 = 姓名/性别/年龄/电话/紧急联系人+电话/咨询状态（进行中/已结束）/咨询开始时间/小节数/自由备注。模型层 `Client` 表与 `Session.client_id` 外键**已存在**（Client 现只有 code/note/status；ClientStatus: active/disabled），缺字段、缺 API。本卡只做后端；前端卡 T-S1.18 验收后派，**本卡不改任何前端文件**。

现有基线：routes.py 有 sessions CRUD/富化列表、groups、export、bulk-delete、segment PATCH、dashboard/summary；测试 82 passed。

## 一、模型扩展（models.py，走既有列自愈 `_heal_missing_columns`，不动旧数据）

`Client` 表加列（全部可空，除 name 业务必填由 API 层校验）：
- `name: str`（String(64)，**必填**，即客户所要求的姓名字段；原 `code` 字段保留作内部代号，新建时若未传 code 则后端自动生成 `C+client_id` 回填）
- `gender: str | None`（String(8)）
- `age: int | None`
- `phone: str | None`（String(32)）
- `emergency_contact: str | None`（String(64)）
- `emergency_phone: str | None`（String(32)）
- `start_date: date | None`（咨询开始时间；SQLite 存 ISO 字符串，API 层用 `str` 传输）
- `session_count_manual: int | None`（小节数手工修正值；为空表示自动计）

`ClientStatus` 语义映射（不改枚举）：`active` = 进行中，`disabled` = 已结束。

## 二、API（routes.py）

1. `GET /clients`：列表按 `status='active'` 优先 + `start_date` 降序（无日期按 created 兜底，**Client 表无 created_at，按 id 降序**）；每条含 `{client_id, code, name, gender, age, phone, emergency_contact, emergency_phone, status, start_date, session_count_manual, session_count_auto, session_count, note}`——`session_count_auto` = 该来访者名下会话数（所有状态），`session_count` = 手工值优先，否则自动值。
2. `POST /clients`：body `{name(必填), code?, gender?, age?, phone?, emergency_contact?, emergency_phone?, start_date?, status?, note?}`；name 空或同用户重名 → 422；start_date 非法格式（非 YYYY-MM-DD）→ 422；age 非整数由 pydantic 自然 422。返回新建完整对象。
3. `PATCH /clients/{id}`：只更新传入字段（`model_fields_set` 口径，仿 SessionPatch）；name 改后重名校验；非法 status（非 active/disabled）→ 422。
4. `DELETE /clients/{id}`：硬删来访者行，名下会话 `client_id` 置 null（记录保留）；返回 `{deleted, affected_sessions: N}`。
5. `PATCH /sessions/{id}` 扩展：`SessionPatch` 加 `client_id: int | None`（显式传字段才更新；非空值校验来访者存在且同用户，否则 404）；返回值加 `client_id`。
6. `GET /sessions`（列表）与 `GET /sessions/{id}`（详情）：富化字段加 `client_id`、`client_name`（无则 null）。
7. `GET /export/sessions`：每条加 `client_id/client_name`。

## 三、测试（app/backend/tests/test_clients.py，新增）

1. CRUD 全链：建（name 必填/重名 422/自动 code 回填）→ 列表（active 优先+session_count 口径：手工值优先）→ 编辑（部分字段/重名 422/非法 status 422）→ 删除（记录归 null、affected_sessions 正确）；
2. SessionPatch 挂 client_id（正常/不存在 404/显式 null 解绑）；
3. 列表/详情/导出带 client_name；
4. 旧库兼容：不传新字段建来访者不炸（列自愈路径由 conftest 既有临时库覆盖即可）。

## 验收标准（自测必须全过并贴证据）

1. `.venv/bin/python -m pytest app/backend/tests -q` → 全过（82 + 新增，报实际数字）。
2. `.venv/bin/ruff check app/backend` → All checks passed。
3. `.venv/bin/python -c "import psyapp.main"` 无异常。
4. `git diff` 只含 `app/backend/**`（含测试）。
5. **完工必须提交**：分支 `task/t-s1.17-clients-api`，commit 前缀 `[T-S1.17]`，自报落 `docs/handoffs/task-T-S1.17-self-report.md` 一并提交（提交是硬验收项）。

## 陷阱与禁止

- **路由前缀陷阱（已犯两次）**：后端路由注册**不带** `/api`（vite 代理剥 `/api`）。例：`@router.get("/clients")`，测试里 `client.get("/clients")`。
- 不改前端任何文件；不改 prompt；不动 `tests/audio/`、`tests/golden/`；不引新依赖；不自动合并/推送/打 tag。
