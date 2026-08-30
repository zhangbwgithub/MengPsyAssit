# Task T-S1.14: 看板交互六项重构（FB-012，前端）

## 背景（后端 T-S1.13 已合 main 并验收，勿动后端）

后端新 API（base 走既有 `/api` 代理）：
- `DELETE /api/groups/{id}?mode=dissolve|with_records`：dissolve=仅解散（记录归未分组，默认）；with_records=组+组内记录全删（级联含音频）。返回 `{deleted, mode, deleted_sessions}`。
- `POST /api/sessions/bulk-delete` body `{"session_ids":[...]}` → `{deleted:[], missing:[]}`。
- `GET /api/export/sessions` → `{exported_at, count, sessions:[...]}`（全量详情，含 segments/record/tags/brief/group_name）。
- `PATCH /api/sessions/{id}/segments/{seq}` body `{"text":"..."}` → `{session_id, seq, word_count}`；后端会重建 cleaned_text。

既有 API 不变：GET /api/sessions（富化列表）、GET /api/sessions/{id}（详情）、PATCH /api/sessions/{id}、DELETE /api/sessions/{id}、groups CRUD。

现状：单文件 `app/frontend/src/App.vue`（Vue3 + Vite，无路由无 Pinia）。左侧 260px 看板（排序/标签筛选/组筛选/按音频折叠/分组管理区在列表下方），右侧纵向「1.上传 → 2.转写对话稿（气泡）→ 3.处理结果」，主题三档（亮/自动/暗，CSS 变量），移动端 375px 适配。上传有 300s 超时+轮询护栏（**不得改动该防护逻辑**）。

## 一、左侧看板重排 + 分组操作上移

1. **分组管理区移到看板顶部**（排序/筛选工具条之上或紧随标题之后），不再放在列表最下面；组行保留组名/标签/成员数/备注，按钮：**编辑**（现有弹层复用）、**删除**。
2. **组删除双模式**：点删除弹确认层（复用现有 modal 机制），提供两个动作按钮：
   - 「仅解散组」→ `DELETE /api/groups/{id}?mode=dissolve`，文案说明记录保留归未分组；
   - 「删除组和包含的记录」→ `DELETE /api/groups/{id}?mode=with_records`，危险样式（红色），文案显示将删除 N 条记录且不可撤销；
   - 任一成功后刷新分组+会话列表。
3. 看板列表区保留现有排序/标签筛选/组筛选/按音频折叠/条目内分组下拉/单条删除。

## 二、记录批量操作：选择/全选/删除/导出

1. 看板工具条加**选择模式**开关（或常显勾选框）：每条记录前加 checkbox；工具条提供「全选/取消全选」（对当前筛选+排序后的可见列表）。
2. 选中 ≥1 条时显示操作条：`已选 N 条 · 删除 · 导出 · 取消`：
   - **删除**：确认弹层列出条数+不可撤销提示 → `POST /api/sessions/bulk-delete`，成功后刷新列表、清空选择；
   - **导出**：`GET /api/export/sessions` 拉全量后，若有选中则过滤出选中 id，生成 JSON 文件浏览器下载（文件名 `mengpsy-records-YYYYMMDD.json`）；无选中时「导出」入口仍在工具条，导出全部记录。
3. 折叠组/音频折叠展开后的子条目同样可勾选；全选覆盖所有可见与折叠内条目（以筛选后全集为准）。

## 三、日历可视化索引

1. 看板加分区「日历」（分组区与列表之间），月视图网格：周一到周日列头、当月日期格、前后月占位；有记录的日期显示圆点+条数；
2. 上一月/下一月按钮 + 「今天」快捷；
3. 点击某天 → 看板列表过滤为该日记录（按 `started_at` **本地时区**取日期，沿用现有 `new Date(value+'Z')` 口径），顶部显示「2026-08-30 · N 条 · 清除」可一键清除日期过滤；日历与标签/组筛选可叠加。

## 四、右侧功能区 Tab 化

1. 右侧主区改为顶部两 Tab：**① 上传/转写区**、**② 记录详情区**。
2. **上传/转写区**：现有上传卡（模式选择/文件/进度/状态/错误）原样保留；处理中/处理完的转写气泡与进度也在此 Tab（即现有「2. 转写对话稿」板块归入此 Tab）。
3. **记录详情区**：展示选中记录的**全部信息**——会话编号、日期时间（本地时区）、来源文件名、时长（MM:SS）、字数、状态、标签徽标、摘要、所属组、咨询记录（概述/咨询师的工作/来访者话题/其他信息，沿用现有折叠块）、以及完整转写稿（见第六条双视图）。摘要/标签内联编辑（复用现有 PATCH 逻辑）。
4. **联动**：点击左侧看板任意记录 → 自动切到「记录详情区」并加载该条；上传完成（done）后自动切到详情区展示新记录（轮询护栏逻辑不动）。
5. 未选中任何记录时详情区显示空态提示。

## 五、转写区双视图（详情区内）

1. 转写稿区顶部 Tab：**气泡视图**（默认，现有气泡布局照搬）/ **表格视图**；
2. 表格视图：表格列 = 轮次(seq) / 说话人（角色标签+颜色）/ 内容（每行一个 textarea 或可编辑单元格）；
3. **精确编辑**：修改内容后该行出现「保存」按钮 → `PATCH /api/sessions/{id}/segments/{seq}`，成功提示并更新本地状态（含字数），失败显示错误；提供「保存全部改动」亦可（可选）；
4. 气泡视图只读浏览，不承担编辑。

## 六、通用要求

1. 主题：新增组件全部走现有 CSS 变量，暗色下可读；375px 窄屏不破版（看板/日历/表格横向可滚动亦可）；
2. 不得改动上传超时/轮询护栏/重试逻辑；不得引新依赖；不改 `vite.config.js`；
3. 允许把 App.vue 拆成若干组件（`src/components/**`），也可保持单文件——以可维护为准。

## 验收标准（自测必须全过并贴证据）

1. `cd app/frontend && npm run build` 成功无 error。
2. `.venv/bin/python -m pytest app/backend/tests -q` 全过（后端零改动，报实际数字）。
3. `.venv/bin/ruff check app/backend` → All checks passed。
4. `git diff` 只含 `app/frontend/src/**` + 自报，无后端、无 `vite.config.js`、无越界。
5. **完工必须提交**：分支 `task/t-s1.14-board-ux`，commit 前缀 `[T-S1.14]`，自报落 `docs/handoffs/task-T-S1.14-self-report.md` 一并提交（提交是硬验收项）。

## 禁止事项

- 不改后端任何文件、不改 prompt、不做真实上传测试（浏览器端到端由大统领验收）、不自动合并/推送/打 tag。
