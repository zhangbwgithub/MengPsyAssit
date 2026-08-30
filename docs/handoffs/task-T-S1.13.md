# Task T-S1.13: 看板 API 扩展——组删除双模式 + 批量删除 + 导出 + 转写段编辑（FB-012，后端）

## 背景

陛下要求看板六项交互升级（FB-012），本卡只做后端。前端卡 T-S1.14 在本卡验收合 main 后再派，**本卡不改任何前端文件**。

现有基线：`app/backend/src/psyapp/routes.py` 已有 sessions 富化列表/详情/PATCH/DELETE 与 groups CRUD（T-S1.11）；`segments.py` 有 `build_cleaned_text(db, session_id)`；`models.py` 有 Session/Segment/Record/Job/SessionGroup。测试基线 68 passed。

## 一、组删除双模式

改 `DELETE /api/groups/{group_id}`，加 query 参数 `mode`：
- `mode=dissolve`（默认，向后兼容）：现有行为——组内会话 `group_id` 置 null，删组；
- `mode=with_records`：先把组内每个会话走**与 `delete_session` 完全相同的硬删级联**（segments/records/jobs/sessions 行 + 音频文件 `Path.unlink(missing_ok=True)`），再删组；
- 其它 mode 值 → 422。建议把单会话硬删抽成内部函数 `_hard_delete_session(db, session, user_id) -> int` 供 `delete_session`、组联删、批量删三处复用（不得复制粘贴三份级联逻辑）。
- 返回 `{"deleted": group_id, "mode": mode, "deleted_sessions": [...]}`（dissolve 时 `deleted_sessions` 为空数组）。

## 二、批量删除

新增 `POST /api/sessions/bulk-delete`，body `{"session_ids": [int, ...]}`：
- 逐个走 `_hard_delete_session`；不属于当前用户或不存在的 id 跳过并记入 `missing`；
- 空列表 → 422；返回 `{"deleted": [...], "missing": [...]}`。

## 三、全量导出

新增 `GET /api/export/sessions`（**路径用 `/api/export/sessions`，不要用 `/sessions/export`**——避免与 `GET /sessions/{session_id:int}` 路由撞车）：
- 返回当前用户全部会话的详情数组，每条与 `GET /api/sessions/{id}` 的 data 同构（含 segments/record/tags/brief/group_id），并补 `original_filename/duration_sec/group_name`；
- 外层 `{"exported_at": iso, "count": n, "sessions": [...]}`；
- 会话按 `started_at` 倒序。

## 四、转写段编辑（表格视图精确编辑的后端支撑）

新增 `PATCH /api/sessions/{session_id}/segments/{seq}`，body `{"text": str}`：
- 会话不存在/非本人 → 404；该 seq 段不存在 → 404；`text` 为空串或纯空白 → 422；
- 写入该段 `cleaned_content = text`（`content` 原文保留不动，保证可追溯）；
- 提交后调 `build_cleaned_text(db, session_id)` 重建 `session.cleaned_text` 并落库（看板字数随之变化）；
- 返回 `{"session_id", "seq", "word_count": len(session.cleaned_text)}`。

## 五、测试（必须新增，不许只改路由不测试）

在 `app/backend/tests/` 新增测试文件（或扩展现有文件）至少覆盖：
1. 组删除 `dissolve`（默认）记录保留、`with_records` 记录+音频级联清零、非法 mode 422；
2. bulk-delete 正常/空列表 422/混入不存在 id 进 missing；
3. 导出端点结构正确、条数与会话数一致、含 segments；
4. 段落 PATCH 正常（cleaned_text 重建、content 不动）、空文本 422、不存在会话/段 404。

## 验收标准（自测必须全过并贴证据）

1. `.venv/bin/python -m pytest app/backend/tests -q` → 全过（68 + 新增，报实际数字）。
2. `.venv/bin/ruff check app/backend` → All checks passed。
3. `.venv/bin/python -c "import psyapp.main"` 无异常。
4. `git diff` 只含 `app/backend/**`（含测试），无前端、无 prompt、无 `.env`、无 `vite.config.js`。
5. **完工必须提交**：分支 `task/t-s1.13-board-api`，commit 前缀 `[T-S1.13]`，自报落 `docs/handoffs/task-T-S1.13-self-report.md` 一并提交（上一卡曾出现完工不提交，此卡提交是硬验收项）。

## 禁止事项

- 不改前端任何文件；不改 clean/omni/record prompt；不动 `tests/audio/`、`tests/golden/`；不引新依赖；不自动合并/推送/打 tag。
