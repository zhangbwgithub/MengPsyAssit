# Task T-S1.15: 工作台统计 API（FB-013，后端）

## 背景

陛下赐参考设计「朗庭心空间·工作台」（KPI 行 + 来访档案 + 数据看板）。本批做 KPI + 数据看板层，本卡只做后端统计聚合端点。前端卡 T-S1.16 在本卡验收合 main 后派，**本卡不改任何前端文件**。

现有基线：`routes.py` 有 sessions 富化列表（含 started_at/duration_sec/tags/brief/status）、groups CRUD、export、bulk-delete、segment PATCH；测试基线 78 passed。

## 一、新增 `GET /api/dashboard/summary`

单一端点返回工作台全部数据（避免前端多请求），结构如下：

```json
{
  "week": {
    "start": "2026-08-24", "end": "2026-08-30",
    "sessions": 12, "sessions_prev": 8,
    "hours": 5.2, "hours_prev": 4.1,
    "avg_minutes": 26.0, "avg_minutes_prev": 30.8
  },
  "totals": {"sessions": 71, "groups": 3},
  "status_dist": [
    {"status": "done", "label": "完成", "count": 65},
    {"status": "failed", "label": "失败", "count": 2},
    {"status": "processing", "label": "处理中", "count": 4}
  ],
  "tag_cloud": [{"tag": "咨询", "count": 5}, ...],
  "trend": [{"date": "2026-08-17", "minutes": 12.5, "sessions": 3}, ...],
  "todos": {"no_brief": 10, "no_tags": 6, "failed": 2}
}
```

### 口径细则（严格遵守）

1. **周窗口**：`week.start` = 本周一 00:00（本地服务器时间即可，与既有 `datetime.now` 口径一致），`week.end` = 本周日。`sessions`/`hours`/`avg_minutes` 统计窗口内**全部会话**（不限 status，failed 也算一次咨询记录；`hours` = Σ duration_sec / 3600 保留 1 位小数，`avg_minutes` = Σ duration_sec / 60 / 条数 保留 1 位，0 条时均为 0）。`*_prev` 同口径统计上一整周（上周一~上周日），供前端算周环比。
2. **totals**：全部会话数 + 全部组数。
3. **status_dist**：按 status 聚合，processing 桶 = uploading+transcribing+cleaning+recording 等所有非 done/failed 中间态之和；顺序固定 [done, processing, failed]，count 为 0 也输出。
4. **tag_cloud**：全部会话 `tags` 数组展开计词频，降序取 Top 20，空 tags 不计。
5. **trend**：近 14 天（含今天）按日聚合：`minutes` = 当日 Σ duration_sec/60 保留 1 位，`sessions` = 当日条数；无记录的日期也要输出（0）。日期升序。
6. **todos**：`no_brief` = done 状态且 (brief 为空或 null) 的条数；`no_tags` = done 状态且 tags 为空数组的条数；`failed` = status=failed 条数。

## 二、测试

`app/backend/tests/test_dashboard.py` 至少覆盖：
1. 空库返回结构完整（所有键在，week 全 0，status_dist 三项 count 0）；
2. 造会话：本周 2 条（含 1 failed）+ 上周 1 条 + 更早 1 条，断言 week.sessions=2 / sessions_prev=1 / hours / avg_minutes / status_dist / trend 对应日期数值；
3. tag_cloud 词频排序正确、Top20 截断；
4. todos 三项口径正确（只对 done 计 no_brief/no_tags）。

## 验收标准（自测必须全过并贴证据）

1. `.venv/bin/python -m pytest app/backend/tests -q` → 全过（78 + 新增，报实际数字）。
2. `.venv/bin/ruff check app/backend` → All checks passed。
3. `.venv/bin/python -c "import psyapp.main"` 无异常。
4. `git diff` 只含 `app/backend/**`（含测试），无前端、无 prompt、无 `.env`。
5. **完工必须提交**：分支 `task/t-s1.15-dashboard-api`，commit 前缀 `[T-S1.15]`，自报落 `docs/handoffs/task-T-S1.15-self-report.md` 一并提交（提交是硬验收项）。

## 禁止事项

- 不改前端任何文件；不改 prompt；不动 `tests/audio/`、`tests/golden/`；不引新依赖；不自动合并/推送/打 tag。
