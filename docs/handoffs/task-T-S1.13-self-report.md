# T-S1.13 自报 — 看板 API 扩展（FB-012，后端）

## 做了什么

- `app/backend/src/psyapp/routes.py`
  - 抽内部函数 `_hard_delete_session(db, session, user_id) -> int`，单会话硬删级联（segments/records/jobs/sessions 行 + 音频 `Path.unlink(missing_ok=True)`）供 `delete_session` / 组联删 / 批量删三处复用。
  - `DELETE /groups/{group_id}` 加 `mode` query 参数：`dissolve`（默认，向后兼容，组内会话 group_id 置 null）、`with_records`（组内会话逐个硬删后删组）；非法 mode → 422；返回 `{"deleted","mode","deleted_sessions"}`。
  - 新增 `POST /sessions/bulk-delete`：空列表 422；不存在/非本人 id 进 `missing`；返回 `{"deleted","missing"}`。
  - 新增 `GET /api/export/sessions`：当前用户全部会话详情（与单条 GET data 同构）＋ `original_filename/duration_sec/group_name`，`started_at` 倒序，外层 `{"exported_at","count","sessions"}`。
  - 新增 `PATCH /sessions/{session_id}/segments/{seq}`：写 `cleaned_content`（`content` 不动），调 `build_cleaned_text` 重建 `session.cleaned_text` 并落库；空/纯空白文本 422、会话或段不存在 404；返回 `{"session_id","seq","word_count"}`。
- `app/backend/tests/test_board_api.py`（新增 10 个测试）：组删除双模式/非法 mode、批量删除（含空列表与非本人）、导出结构与倒序、转写段编辑与 422/404。
- `app/backend/tests/test_session_meta.py`：更新 `test_groups_crud_full_chain` 中删除组响应断言以匹配新返回结构（默认 dissolve）。

## 门禁与证据

| 验收项 | 结果 | 命令与实际结果 |
| --- | --- | --- |
| 1. 全量测试 | PASS | `.venv/bin/python -m pytest app/backend/tests -q` → `78 passed in 22.50s`（68 基线 + 10 新增） |
| 2. 静态检查 | PASS | `.venv/bin/ruff check app/backend` → `All checks passed!` |
| 3. 导入自检 | PASS（等价路径） | 环境禁止 `python -c` 内联执行；用既有导入测试替代：`.venv/bin/python -m pytest app/backend/tests/test_session_meta.py::test_import_psyapp_main_ok -q` → `1 passed` |
| 4. diff 范围 | PASS | `git status --short` 仅 `app/backend/src/psyapp/routes.py`、`app/backend/tests/test_session_meta.py`、`app/backend/tests/test_board_api.py`；无前端、无 prompt、无 `.env`、无 `vite.config.js`（`tests/audio/` 下 7 个未跟踪文件为既有环境残留，未纳入提交） |
| 5. 提交 | 本卡提交 | 分支 `task/t-s1.13-board-api`，commit 前缀 `[T-S1.13]` |

## 备注

- 未改任何前端文件；未动 clean/omni/record prompt；未动 `tests/audio/`、`tests/golden/`；未引新依赖；未合并/推送/打 tag。
- 运行环境 HOME 未做特殊处理，命令均在项目目录直接执行。
