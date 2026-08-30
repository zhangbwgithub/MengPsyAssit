# T-S1.15 自报：工作台统计 API（FB-013，后端）

## 做了什么

- `app/backend/src/psyapp/routes.py`：新增 `GET /api/dashboard/summary` 单端点，返回工作台全部数据（week / totals / status_dist / tag_cloud / trend / todos），供后续 T-S1.16 前端直接消费，避免多请求。聚合实现在 `_dashboard_summary_data`（单用户全量内存聚合，S0 数据量足够），严格按口径：
  - **week**：本周一 00:00 ~ 本周日（本地服务器时间，与既有 `datetime.now` 口径一致），`sessions`/`hours`/`avg_minutes` 统计窗口内全部会话（不含 status 过滤，failed 也算一次记录）；`hours` = Σ duration_sec/3600 保留 1 位，`avg_minutes` = Σ duration_sec/60/条数 保留 1 位，0 条时均为 0；`*_prev` 同口径统计上一整周。
  - **totals**：全部会话数 + 全部组数。
  - **status_dist**：processing 桶 = 所有非 done/failed 中间态之和，顺序固定 [done, processing, failed]，count 为 0 也输出。
  - **tag_cloud**：全部会话 tags 数组展开词频，降序取 Top 20（同频按标签名升序保证稳定），空 tags 不计。
  - **trend**：近 14 天（含今天）逐日聚合，minutes/sessions，无记录日期补 0，日期升序。
  - **todos**：`no_brief`/`no_tags` 仅对 done 状态计（brief 为空/null、tags 为空数组），`failed` = status=failed 条数。
- 未改动任何前端文件、prompt、`tests/audio/`、`tests/golden/`；未引新依赖。
- `app/backend/tests/test_dashboard.py` 新增 4 个离线测试。

## 跑了什么命令

```bash
HOME=/home/houmo .venv/bin/python -m pytest app/backend/tests -q
```
结果：`82 passed in 22.03s`（78 基线 + 4 新增）。

```bash
HOME=/home/houmo .venv/bin/ruff check app/backend
```
结果：`All checks passed!`。

```bash
HOME=/home/houmo .venv/bin/python -c "import psyapp.main"
```
结果：无异常。

## 验收对照

1. pytest 全过，82 passed（78 + 4）—— PASS。
2. ruff All checks passed —— PASS。
3. `import psyapp.main` 无异常 —— PASS。
4. `git diff` 只含 `app/backend/**`（routes.py + 新增 tests/test_dashboard.py），无前端、无 prompt、无 `.env` —— PASS（工作区另有编排方未提交的 `tests/audio/` 文件与 `docs/handoffs/CURRENT.md`，不属于本卡，未纳入提交）。
5. 完工提交：分支 `task/t-s1.15-dashboard-api`，commit 前缀 `[T-S1.15]`，本自报一并提交 —— PASS。

## 测试覆盖明细（tests/test_dashboard.py）

1. `test_dashboard_summary_empty_library_returns_full_structure`：空库返回结构完整（6 个顶层键齐、week 全 0、status_dist 三项 count 0、trend 14 天全 0）。
2. `test_dashboard_summary_week_totals_status_dist_and_trend`：本周 2 条（含 1 failed）+ 上周 1 条 + 更早 1 条，断言 week.sessions=2 / sessions_prev=1 / hours=1.5 / hours_prev=0.5 / avg_minutes=45.0 / avg_minutes_prev=30.0 / totals / status_dist / trend 对应日期数值；更早记录不在 14 天窗口。
3. `test_dashboard_tag_cloud_frequency_order_and_top20`：词频降序（hot 排第一）、空 tags 不计、21 个不同标签截断到 Top20（含 t00、裁掉 t19）。
4. `test_dashboard_todos_only_done_counts_no_brief_no_tags`：no_brief=2、no_tags=2、failed=1，processing/failed 态不计入 no_brief/no_tags。

## 未验证 / 风险

- 周环比实际展示效果由大统领实测验收；本文仅保证口径与数值正确。
- 全量内存聚合在 S0 单用户数据量下足够，数据规模增长后的 SQL 聚合优化未做（不急，属超范围）。
