# Task T-S1.18: 来访者档案前端（FB-014 客户需求①③，批次 A 前端）

## 背景（后端 T-S1.17 已合 main 并验收，勿动后端）

后端新 API（**前端一律经 `/api` 代理调用**，后端注册路径不带 /api）：
- `GET /api/clients` → `{clients: [{client_id, code, name, gender, age, phone, emergency_contact, emergency_phone, status(active=进行中/disabled=已结束), start_date, session_count_manual, session_count_auto, session_count, note}]}`（active 优先）；
- `POST /api/clients` `{name(必填), gender?, age?, phone?, emergency_contact?, emergency_phone?, start_date?, status?, note?}`（重名/空名 422）；
- `PATCH /api/clients/{id}`（部分字段）；`DELETE /api/clients/{id}` → `{deleted, affected_sessions}`（记录保留、client_id 置 null）；
- `PATCH /api/sessions/{id}` 已支持 `{client_id: int|null}`；`GET /api/sessions`、`GET /api/sessions/{id}`、`GET /api/export/sessions` 均带 `client_id/client_name`。

## ⚠️ UI 设计基准（陛下拍板，强制遵守）

参考 atlantic.vc 版式 + `/home/houmo/hermes_work/web/idh_dashboard_20260827.html` 质感：
1. 字体：`-apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text"` 系统栈；
2. 色板：亮底 #F4F5F7/卡 #FFFFFF，暗底 #1C1F26/卡 #262B35，主色 #4A68D8（暗 #8A9BF0），状态色灰调（ok #6FA87C / bad #C97A7A / warn #C99A5B / info #7A9CC9）——接入既有 CSS 变量体系；
3. 形态：卡圆角 10-11px、胶囊 99px、轻阴影、无重边框；
4. **禁止 emoji 图标、禁止图片**：图标一律单色 SVG 线条（内联 <svg>）或纯排版符号；**同时把现有工作台 KPI 卡的 📅⏱️🎯🗂️ emoji 一并移除**（改排版式小字标题+大数字，或单色 SVG）；
5. 图表延续纯 SVG。
本卡改动范围内遇到既有 emoji 图标顺手清掉，不扩范围。

## 一、左列来访者名单（客户需求三）

现有左侧看板 `<aside>` 顶部（分组区之上或并列，以信息架构合理为准）新增「来访」区：
1. 来访者列表：显示姓名 + 状态徽标（进行中绿/已结束灰）+ 小节数；**进行中优先**（API 已排序）；点击来访者 → 看板记录列表过滤为该来访者的记录（与既有标签/组/日历筛选可叠加，清除方式一致）；
2. 「新增来访」按钮 → 表单弹层：姓名（必填）、性别（单选：女/男/其他）、年龄、电话、紧急联系人、紧急联系人电话、咨询开始时间（date 输入）、状态、备注；保存调 `POST /api/clients`，422 显示错误；
3. 每行操作：编辑（同表单弹层回填，`PATCH`）、删除（确认弹层显示「名下 N 条记录将保留并归为未关联」，`DELETE`）；
4. 记录条目与详情区显示来访者姓名徽标；看板新增「来访筛选」（复用组筛选的下拉样式）。

## 二、记录挂来访者

1. 记录条目内联下拉「归属来访者」（仿既有分组下拉），调 `PATCH /api/sessions/{id}` 的 `client_id`；
2. 上传区：上传表单加可选「来访者」下拉（默认不选），上传后自动把新会话挂上（上传成功后调一次 PATCH）；
3. 详情区显示「来访者」字段（可点击切换下拉）。

## 三、通用要求

1. 深色主题全适配（CSS 变量）；375px 窄屏不破版；
2. 不动上传超时/轮询护栏；不引新依赖；不改 `vite.config.js`；不改后端；
3. 记录看板/工作台既有功能零回归（尤其：分组置顶、日历、批量操作、双 Tab、转写双视图、工作台图表）。

## 验收标准（自测必须全过并贴证据）

1. `cd app/frontend && npm run build` 成功无 error。
2. `.venv/bin/python -m pytest app/backend/tests -q` 全过（后端零改动）。
3. `.venv/bin/ruff check app/backend` → All checks passed。
4. `git diff` 只含 `app/frontend/src/**` + 自报。
5. **完工必须提交**：分支 `task/t-s1.18-clients-ui`，commit 前缀 `[T-S1.18]`，自报落 `docs/handoffs/task-T-S1.18-self-report.md` 一并提交（提交是硬验收项）。

## 禁止事项

- 不改后端任何文件、不改 prompt、不做真实上传测试（浏览器端到端由大统领验收）、不自动合并/推送/打 tag。
