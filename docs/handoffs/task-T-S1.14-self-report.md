# T-S1.14 自报：看板交互六项重构（FB-012，前端）

## 做了什么

单文件 `App.vue`（2561 行）重构为组件体系，落地六项交互，上传超时/轮询护栏逻辑保持原样（仅新增 done 后切详情一处，护栏参数/重试/在途保护未动）：

- `App.vue`：编排器，保留主题、上传/轮询、会话/分组加载与编辑逻辑；新增右侧双 Tab 状态、组删除双模式弹层、批量删除/导出、转写段 PATCH。
- `src/components/BoardSidebar.vue`：左侧看板。分组管理区移到顶部（组名/标签/成员数/备注 + 编辑/删除）；日历索引（月网格 + 圆点条数 + 前后月占位 + 上/下月 + 今天 + 点击过滤 + 清除条）；排序/标签/组筛选/日期过滤叠加；按音频折叠与分组折叠；选择模式 + 每条 checkbox + 全选/取消全选 + 已选操作条（删除/导出/取消）；条目内分组下拉与单条删除保留。
- `src/components/CalendarMini.vue`：月视图日历（周一~周日列头、42 格），按 `started_at` 本地时区（沿用 `new Date(value+'Z')`）统计每天条数。
- `src/components/UploadPanel.vue`：① 上传/转写区——原上传卡（模式/文件/进度/状态/错误）+ 转写气泡（处理中/处理完）。
- `src/components/DetailPanel.vue`：② 记录详情区——会话编号/本地日期时间/来源文件/时长/字数/状态/标签徽标/摘要/所属组/咨询记录折叠块/完整转写稿；摘要/标签内联编辑（复用 PATCH）；空态提示。
- `src/components/TranscriptBubbles.vue`：气泡视图（原布局照搬，只读）。
- `src/components/TranscriptTable.vue`：表格视图（轮次/说话人角色标签+颜色/内容 textarea），行内「保存」+「保存全部改动」→ `PATCH /api/sessions/{id}/segments/{seq}`。
- `src/utils/format.js`、`src/utils/speakers.js`：本地时区格式化与说话人调色板共用工具。

联动：点看板任意记录自动切「记录详情区」并加载详情；上传 done 后自动切详情展示新记录（轮询护栏不动）。

## 跑了什么命令

```bash
cd app/frontend && npm run build
```
结果：`✓ built in 493ms`，25 modules transformed，无 error。

```bash
.venv/bin/python -m pytest app/backend/tests -q
```
结果：`78 passed in 21.62s`（后端零改动）。

```bash
.venv/bin/ruff check app/backend
```
结果：`All checks passed!`。

## 验收对照

1. `npm run build` 成功无 error —— PASS。
2. pytest 78 个全过 —— PASS。
3. ruff All checks passed —— PASS。
4. `git diff` 仅含 `app/frontend/src/**`（App.vue 重写 + `components/` + `utils/` 新增）+ 本自报；无后端、无 `vite.config.js` —— PASS（工作区另有编排方未提交的 `docs/handoffs/CURRENT.md` 与 `tests/audio/` 改动，不属于本卡，未纳入提交）。
5. 分支 `task/t-s1.14-board-ux`，提交前缀 `[T-S1.14]`，本自报一并提交 —— PASS。

## 未验证 / 风险

- 浏览器端到端（上传真实音频、日历点击、批量删除、导出下载、段编辑落库）由大统领验收——本条未做真实上传测试。
- 大文件上传 300s 超时与轮询 10s/3 连败护栏仅做逻辑走查与 build，未在浏览器实测（原逻辑未改动）。
