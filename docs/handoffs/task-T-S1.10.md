# Task T-S1.10: 前端上传挂起防护修复 + 左侧上传/分析记录看板（FB-010）

## 背景与实证（大统领诊断取证，2026-08-29，勿重复侦查）

陛下实测：会话 49（12:03）、50（12:08）均 done 之后，再传第三个**永久卡住**。取证结论：

- 12:08–12:25 后端访问日志零 `POST /sessions`、`data/audio/` 零孤儿文件 → 请求从未到达后端落盘层，死在浏览器/代理链路。
- 服务端与链路均健康（health 200、连续上传 3 段含 65s idle 全部成功、5.1s keep-alive 竞态窗口 8 连发无异常、无 Service Worker）。
- 根因是**前端零防护**：
  - ① `upload()` 的 POST fetch 无超时 → 请求挂起则「处理中…」永久卡死，无错误提示；
  - ② `startPolling()` 的 GET fetch 无超时、无在途护栏 → 任一请求挂起后 3 秒定时器继续发新请求，逐个挂起，耗尽浏览器同源 6 连接上限，后续所有请求（含新上传）永久排队 = 「点下一个上传就卡住」；
  - ③ 触发条件为客户端网络瞬时抖动，服务端难以复现，但前端必须自愈。

## Part A：上传挂起防护（修 `app/frontend/src/App.vue`）

1. **上传超时**：`upload()` 内给 `fetch('/api/sessions', …)` 挂 `AbortController`，超时 **300 秒**（局域网大文件上传留余量）；超时即 `abort`，走既有 catch → `error.value` 显示「上传请求超时，请检查网络后重试」，`uploading.value = false`（按钮/文件框恢复可用）。
2. **轮询超时 + 在途护栏**：`startPolling()` 内：
   - 每次轮询 fetch 挂 `AbortController`，超时 **10 秒**；
   - 加在途标志（如 `pollingInFlight` ref）：上一个轮询请求未结束时本次定时触发**直接跳过**，不得叠加发出；
   - **连续失败退出**：连续 3 次轮询失败（含超时/非 200/非 ok）→ `stopPolling()`，`uploading.value = false`，`error.value` 显示「查询会话状态失败，请刷新页面或点击重试」；任一次成功则计数归零。
3. **错误框重试**：复用现有 `retry()` 入口即可，不改语义。
4. 不改任何后端代码、不改轮询间隔（3 秒）、不改状态机与进度条渲染逻辑、不改气泡样式。

## Part B：左侧「上传与分析记录看板」（同文件 + 布局调整）

1. **布局**：页面主体改为左右两栏——**左侧固定看板栏**（宽度约 260px，窄屏 <768px 时落到主区上方，不得破版），右侧保留现有上传区/对话稿区/结果区不变。
2. **看板数据**：`GET /api/sessions` 已返回 `{session_id, status, started_at}`，直接使用；进入页面时加载一次，每次上传发起后刷新一次，另加一个手动「刷新」按钮。不新增后端接口。
3. **看板条目**：每条显示 `#会话编号`、状态徽标（done=绿「完成」/ failed=红「失败」/ uploading|transcribing=蓝「处理中」+ 小转圈）、开始时间（本地时区，`MM-DD HH:MM` 格式）。按时间倒序（接口已倒序，直接渲染）。
4. **点击回看**：点击任一条目 → `GET /api/sessions/{id}`，把返回数据注入现有 `sessionData`/`sessionStatus`，右侧主区按现有渲染逻辑显示该会话的对话稿与记录（复用现有渲染，不为看板另写渲染分支）。回看期间若该会话仍在处理中，按现有逻辑恢复轮询（`startPolling`，用该会话 id）。
5. 空列表显示「暂无记录」占位文案。

## 验收标准（Reasonix 自测必须全过并贴证据）

1. `cd app/frontend && npm run build` 成功，无 error（warning 可）。
2. `.venv/bin/python -m pytest app/backend/tests -q` → 59 passed（后端零改动，数字必须与基线一致）。
3. `.venv/bin/ruff check app/backend` → All checks passed（后端零改动）。
4. `git diff` 自查：只含 `app/frontend/src/App.vue`（如需拆组件可加前端新文件，但不得动 `vite.config.js`/后端/`tests/`/`docs/`（自报除外）），无越界。
5. 自报落 `docs/handoffs/task-T-S1.10-self-report.md`，随分支提交。

## 禁止事项

- 不改后端任何文件（`app/backend/**` 全部不动）。
- 不引新前端依赖（不上 axios/pinia/router/vite-plugin-pwa）。
- 不改 `vite.config.js`、不改 `OMNI_TRANSCRIBE_PROMPT`、不碰 `tests/audio/` 下未跟踪音频。
- 不做真实 API 调用测试（浏览器端到端由大统领验收）。
- 不自动合并/推送/打 tag；提交到分支 `task/t-s1.10-upload-stuck-board`，commit message 前缀 `[T-S1.10]`。
