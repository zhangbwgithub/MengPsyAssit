# T-S1.10 自报：前端上传挂起防护修复 + 左侧上传/分析记录看板（FB-010）

## 做了什么

只改 `app/frontend/src/App.vue` 一个文件，后端零改动。

### Part A：上传挂起防护

1. `upload()`：POST `fetch('/api/sessions', …)` 挂 `AbortController`，超时 **300 秒**；超时 `abort` 走既有 catch，`err.name === 'AbortError'` 时 `error.value = '上传请求超时，请检查网络后重试'`，`uploading.value = false`，`finally` 里 `clearTimeout` 防泄漏。
2. `startPolling()`：
   - 新增 `pollOnce()`：每次轮询 GET 挂 `AbortController`，超时 **10 秒**；
   - 新增在途标志 `pollingInFlight`：上一个请求未结束时本次定时触发直接 `return` 跳过，不叠加请求；
   - 连续失败退出：`pollFailures` 计数，连 3 次失败（超时/非 200/非 ok 均算）→ `stopPolling()`、`uploading.value = false`、`error.value = '查询会话状态失败，请刷新页面或点击重试'`；任一次成功计数归零。
   - 轮询间隔维持 3 秒不变，成功/失败状态处理逻辑不变。
3. 错误框复用现有 `retry()` 入口，未改语义。

### Part B：左侧「上传与分析记录看板」

1. 布局：`<main>` 改 `.dashboard` 双栏——左侧 `<aside class="board">`（260px，`position: sticky`），右侧 `.main-panel` 原封不动装上传区/对话稿区/结果区；`max-width` 从 960px 提到 1120px。`@media (max-width: 767px)` 时看板落到主区上方、全宽、取消 sticky。
2. 数据：`GET /api/sessions` 返回的 `{sessions: [{session_id, status, started_at}]}` 直接使用；`onMounted` 加载一次，每次上传发起后刷新，看板头手动「刷新」按钮。
3. 条目：`#编号` + 状态徽标（done=绿「完成」/ failed=红「失败」/ 其余=蓝「处理中」+ 小转圈）+ 开始时间（本地时区 `MM-DD HH:MM`）；接口已倒序，直接渲染。
4. 点击回看：`selectSession(id)` → `GET /api/sessions/{id}`，把 `data` 注入 `sessionData`、`status` 注入 `sessionStatus`，`sessionId` 设为该 id，右侧按现有渲染逻辑显示；若该会话 `uploading/transcribing` 仍处理中，`startPolling()` 恢复轮询（轮询 done/failed 时同步刷新看板列表）。
5. 空列表显示「暂无记录」；列表加载失败在看板内显示错误，不污染主区 error。

## 跑了什么命令 / 结果

- 前端构建：`cd app/frontend && npm run build` → **✓ built in 394ms**，无 error。
- 后端测试：`.venv/bin/python -m pytest app/backend/tests -q` → **59 passed in 12.90s**（与基线一致）。
- 后端静态：`.venv/bin/ruff check app/backend` → **All checks passed!**。
- git diff 自查：只含 `app/frontend/src/App.vue` + 本自报，无越界。

## 逐条对照验收标准

| 项 | 结果 | 说明 |
| -- | -- | -- |
| 1. npm run build 成功无 error | PASS | `✓ built in 394ms`，10 modules，无 error |
| 2. pytest 59 passed（基线一致） | PASS | `59 passed in 12.90s`，后端零改动 |
| 3. ruff All checks passed | PASS | `All checks passed!`，后端零改动 |
| 4. git diff 只含 App.vue | PASS | diff 只含 `app/frontend/src/App.vue`，未动 vite.config.js/后端/tests/docs |
| 5. 自报落 docs/handoffs/ | PASS | 本文件，随分支提交 |

## 备注

- 不做真实 API 调用测试（浏览器端到端由大统领验收）。
- `tests/audio/` 下 04/05/06/07/08/09 音频与标注文件为工作区既有未跟踪文件，不在本卡范围，未纳入提交。
- 提交到分支 `task/t-s1.10-upload-stuck-board`，commit message 前缀 `[T-S1.10]`。
