# Task T-S1.12: 记录标签/摘要编辑 + 看板排序筛选/分组/删除 + 深色主题（FB-011，前端）

## 背景（后端 T-S1.11 已合 main 并真 API 验收，勿动后端）

后端已就绪的 API（base 走既有 `/api` 代理）：
- `GET /api/sessions` 富化：每条含 `session_id/status/started_at/original_filename/duration_sec/word_count/tags[]/brief/group_id/group_name`；
- `GET /api/sessions/{id}` 详情含 `tags/brief/group_id` + segments + record；
- `PATCH /api/sessions/{id}`：body 可选 `{tags: str[], brief: str(≤100), group_id: int|null}`，只更新传入字段，返回 `{session_id,tags,brief,group_id}`；brief>100 → 422、非法 group_id → 404；
- `DELETE /api/sessions/{id}`：硬删（含音频），返回 `{deleted}`；
- `GET /api/groups`：`[{group_id,name,tags[],note,created_at,member_count}]` 倒序；`POST /api/groups` `{name,tags?,note?}`（重名 422）；`PATCH /api/groups/{id}`；`DELETE /api/groups/{id}`（删组不删记录，成员归未分组）。

## 一、记录卡：标签/摘要生成、可编辑、可折叠可展开（改 `app/frontend/src/App.vue`，可拆组件）

1. 右侧「3. 处理结果」区（及回看详情）增加**摘要行 + 标签行**：
   - 摘要：优先显示会话 `brief`；无则截 `record.summary` 前 100 字兜底；
   - 标签：显示 `tags` 数组为徽标；为空显示「无标签」。
2. **可编辑**：摘要与标签各带「编辑」入口（内联输入即可）——标签用逗号分隔输入；摘要输入限制 ≤100 字（超出禁止提交并提示）；保存调 `PATCH /api/sessions/{id}`，成功后刷新本地状态与看板列表；失败（422/404）显示错误。
3. **可折叠可展开**：结果区各板块（概述/咨询师工作/来访者话题/其他信息）或整卡可折叠/展开（默认展开，点击标题收起），纯前端状态。

## 二、左侧看板优化

1. **排序/筛选**：看板顶部加排序下拉（上传时间 / 时长 / 字数 / 文件名，均可升/降序）+ 标签筛选（多选现有 tags 去重集合；组名筛选可选）。排序筛选**纯前端**对已加载列表计算，默认时间倒序（现状）。
2. **同音频折叠 + 分组**：
   - 同 `original_filename` 的记录可折叠成一行（组头显示文件名+条数），展开见各条；提供「按音频折叠」开关；
   - **分组管理**：看板加「分组」区——列出 `/api/groups`（组名/标签/备注/成员数），支持新建（弹层输入组名/标签/备注）、编辑（同三字段）、删除（先确认）；
   - 记录条目支持「移入分组/移出分组」（调 `PATCH` 的 `group_id`），组内记录在折叠组头下聚合显示组名/标签/备注。
3. **删除记录**：每条记录带删除入口，点击先弹确认框（显示会话编号+文件名），确认后 `DELETE /api/sessions/{id}`，成功后从列表移除；组删除同样先确认。
4. 看板条目补充显示：来源文件名（可截断）、时长（`MM:SS`）、字数。

## 三、深色版主题

1. 加主题切换（页头按钮或开关，亮/暗两档），选择持久化 `localStorage`，默认跟随系统 `prefers-color-scheme`。
2. 用 CSS 变量实现：暗色下背景/卡片/文字/边框/主色/状态色成体系，对话稿气泡、进度条、状态徽标、看板、表单在暗色下清晰可读、对比度达标；不得只换背景不换前景导致不可读。
3. 375px 窄屏下深色同样不破版。

## 验收标准（自测必须全过并贴证据）

1. `cd app/frontend && npm run build` 成功无 error。
2. `.venv/bin/python -m pytest app/backend/tests -q` → 68 passed（后端零改动）。
3. `.venv/bin/ruff check app/backend` → All checks passed（后端零改动）。
4. `git diff` 只含前端（`app/frontend/src/**`，可新增组件/样式文件）+ 自报，无后端、无 `vite.config.js` 改动、无越界。
5. 自报落 `docs/handoffs/task-T-S1.12-self-report.md` 随分支提交。

## 禁止事项

- 不改后端任何文件、不改 clean/omni/record prompt、不改 `vite.config.js`、不引新依赖。
- 不做真实上传测试（浏览器端到端由大统领验收）。
- 不自动合并/推送/打 tag；分支 `task/t-s1.12-board-theme`，commit 前缀 `[T-S1.12]`。
