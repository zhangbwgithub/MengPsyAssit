# T-S1.16 自报：工作台页（FB-013，前端）

## 做了什么

- `app/frontend/src/components/Workbench.vue`（新增）：工作台页三块自上而下 KPI 行 → 图表行 → 待办行，纯 CSS/SVG 实现，未引入图表库：
  - **KPI 行（4 卡）**：本周咨询数 / 本周咨询时长（小时）/ 平均单次时长（分钟）三卡带周环比（↑绿 / ↓红 / 持平灰，算百分比；上期为 0 时显示「较上周有增长/下降」不给无意义百分比）；累计记录数卡副文案「共 N 个分组」；整行上方标注统计窗口 `week.start ~ week.end`。
  - **图表行（2×2）**：
    1. 咨询状态分布：SVG donut（stroke-dasharray 分段，段间留白），图例带数值与占比，完成=绿 / 处理中=蓝 / 失败=红，全 0 显示「暂无数据」空态；
    2. 议题标签词云：count 线性映射 12~28px，亮度随词频线性变化（HSL 亮度 24%~55%，浅/深两主题都可读），确定性色相（同数据渲染稳定），空则空态；
    3. 近 14 天趋势：SVG 折线 + 面积渐变填充 + 圆点悬停 title，x 轴稀疏标注（14 天每 3 天 + 末日），y 轴分钟三档刻度；
    4. 本周工作量（第 4 格补位）：近 7 天每日条数迷你条形（复用 trend 后 7 天，无额外请求）。
  - **待办行**：待补摘要 / 待补标签 / 失败待处理三卡，各带计数角标（0 置灰），点击 emit `goto-todo`。
  - **375px 窄屏**：KPI 卡 2×2（≤960px 起）→ 图表/待办纵向堆叠（≤640px），不破版。
- `app/frontend/src/App.vue`：页头加「记录看板 / 工作台」胶囊切换（纯前端状态 `appView`，看板为默认且全部既有内容原样保留）；工作台懒加载 `GET /api/dashboard/summary`，加载中显示「加载中…」，失败显示错误 + 重试按钮；待办卡点击 → 切回记录看板（不做精确筛选联动）。未改动上传/轮询护栏、主题切换与看板下所有既有逻辑。
- 未改动后端任何文件、prompt、`tests/audio/`、`tests/golden/`；未引新依赖；未改 `vite.config.js`。

## 跑了什么命令

```bash
cd app/frontend && npm run build
```
结果：`✓ built`，无 error（vite v5.4.21）。

```bash
HOME=/home/houmo .venv/bin/python -m pytest app/backend/tests -q
```
结果：`82 passed in 22.09s`（后端零改动）。

```bash
HOME=/home/houmo .venv/bin/ruff check app/backend
```
结果：`All checks passed!`。

## 验收对照

1. `npm run build` 成功无 error —— PASS。
2. pytest 全过（82 passed）—— PASS。
3. ruff All checks passed —— PASS。
4. `git diff` 只含 `app/frontend/src/App.vue`（修改）+ 新增 `app/frontend/src/components/Workbench.vue` + 本自报，无后端、无 prompt、无 `.env` —— PASS（工作区另有编排方未提交的 `tests/audio/*` 文件，不属于本卡，未纳入提交）。
5. 完工提交：分支 `task/t-s1.16-workbench`，commit 前缀 `[T-S1.16]`，本自报一并提交 —— PASS。

## 未验证 / 风险

- 浏览器端实际渲染与交互（两主题可读性、375px 布局、点击下钻、真实数据展示）由大统领端到端实测验收；本文仅保证构建通过、组件编译无错、数据字段与后端 API 契约对齐。
- `color-mix()` 用于条形图填充渐变（CSS 自定义属性与 `color-mix` 在现代 Chromium/Firefox/Safari 均支持），如目标浏览器覆盖较旧内核可能降级，但不影响布局。
