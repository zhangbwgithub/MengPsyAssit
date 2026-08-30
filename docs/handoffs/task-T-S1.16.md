# Task T-S1.16: 工作台页（FB-013，前端）

## 背景（后端 T-S1.15 已合 main 并验收，勿动后端）

后端新 API：`GET /api/dashboard/summary` 返回（base 走既有 `/api` 代理）：

```json
{
  "week": {"start","end","sessions","sessions_prev","hours","hours_prev","avg_minutes","avg_minutes_prev"},
  "totals": {"sessions": N, "groups": N},
  "status_dist": [{"status","label","count"} × 3],
  "tag_cloud": [{"tag","count"} ...Top20],
  "trend": [{"date","minutes","sessions"} × 14],
  "todos": {"no_brief","no_tags","failed"}
}
```

现状：Vue3 单页（`src/App.vue` 编排器 + `components/`），页头含主题三档切换。深色主题走 CSS 变量体系。

## 一、页面结构：顶层加「记录看板 / 工作台」切换

1. 页头加两个顶层入口（胶囊/下划线式均可）：「记录看板」（默认，现有全部内容原样）与「工作台」（新增）；切换为纯前端状态，记录看板的所有既有功能零回归。
2. 「工作台」页自上而下三块：**KPI 行 → 图表行 → 待办行**。

## 二、KPI 行（4 卡，周环比箭头）

卡片 = 图标（emoji 或 SVG 均可）+ 大数字 + 标题 + 环比小字：
1. **本周咨询数** `week.sessions`，环比 `sessions_prev`（↑绿/↓红/持平灰，算百分比）；
2. **本周咨询时长** `week.hours` 小时，同上；
3. **平均单次时长** `week.avg_minutes` 分钟，同上；
4. **累计记录数** `totals.sessions`，副文案 `共 N 个分组`（本期占位，后续换「进行中来访者」）。
卡片右上角小字标注统计窗口 `week.start ~ week.end`（放第 1 卡或整行上方均可）。

## 三、图表行（2×2 网格，纯 CSS/SVG 实现，禁止引入图表库）

1. **咨询状态分布（环形图）**：SVG donut（stroke-dasharray 分段），图例带数值与占比；配色：完成=绿、处理中=蓝、失败=红；全 0 时显示空态「暂无数据」。
2. **议题标签（词云）**：`tag_cloud` 按 count 映射字号（如 12~28px 线性）与透明度，随机色系但须两主题下可读；空则空态。
3. **近 14 天咨询时长（趋势）**：SVG 折线 + 面积填充（参考设计样式），x 轴日期稀疏标注（每 2~3 天），y 轴分钟；点悬停可选做。
4. **本周工作量条形（可选）**：若 2×2 有空位，用近 7 天每日条数迷你条形补足；否则第 4 格放「分组概览」（组名+成员数列表，数据来自既有 `/api/groups`）。

## 四、待办行（可点击下钻）

三张待办卡：`待补摘要 no_brief` / `待补标签 no_tags` / `失败待处理 failed`，各带计数角标；点击任一项 → 自动切回「记录看板」页（保持简单：切换页面即可，不必做精确筛选联动）。

## 五、通用要求

1. 深色主题全适配（CSS 变量）；375px 窄屏：KPI 卡 2×2、图表纵向堆叠，不破版；
2. 数据加载失败显示错误提示 + 重试按钮；加载中显示骨架/「加载中…」；
3. 不引新依赖；不改 `vite.config.js`；不改上传/轮询护栏；记录看板功能零回归。

## 验收标准（自测必须全过并贴证据）

1. `cd app/frontend && npm run build` 成功无 error。
2. `.venv/bin/python -m pytest app/backend/tests -q` 全过（后端零改动）。
3. `.venv/bin/ruff check app/backend` → All checks passed。
4. `git diff` 只含 `app/frontend/src/**` + 自报。
5. **完工必须提交**：分支 `task/t-s1.16-workbench`，commit 前缀 `[T-S1.16]`，自报落 `docs/handoffs/task-T-S1.16-self-report.md` 一并提交（提交是硬验收项）。

## 禁止事项

- 不改后端任何文件、不改 prompt、不做真实上传测试（浏览器端到端由大统领验收）、不自动合并/推送/打 tag。
