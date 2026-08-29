# Task T-S1.10-R1: 看板时间显示修正——UTC 原值 → 北京时间（FB-010）

## 背景（大统领验收 T-S1.10 时实测发现，勿重复侦查）

任务卡 T-S1.10 Part B 契约要求看板条目开始时间为「本地时区，`MM-DD HH:MM` 格式」。
实测偏差：会话 73 创建于北京时间 13:19（后端存 `2026-08-29T05:19:xx` naive UTC），
看板显示 `05:19`——**差 8 小时**。

根因：后端 `started_at` 为 naive UTC，JSON 输出无 `Z`/时区后缀；前端 `formatStartedAt`
用 `new Date(value)` 解析，JS 把无时区后缀的 ISO 串当**本地时间**处理，
于是 UTC 数字被原样当本地时间显示。

## 契约（只改前端 `app/frontend/src/App.vue` 的 `formatStartedAt`）

1. `formatStartedAt(value)` 把入参按 **UTC** 解释后再转浏览器本地时区显示：
   做法自定（如 `new Date(value + 'Z')`，或手工拼 UTC 时间戳），
   输出仍为本地时区 `MM-DD HH:MM`（`pad` 补齐规则不变）。
   解析失败仍返回 `'—'`。
2. 不改后端、不改接口、不改其他前端逻辑与样式。

## 验收标准

1. `cd app/frontend && npm run build` 成功。
2. `.venv/bin/python -m pytest app/backend/tests -q` → 59 passed（后端零改动）。
3. `.venv/bin/ruff check app/backend` → All checks passed。
4. `git diff` 只含 `App.vue` + 自报追加（`docs/handoffs/task-T-S1.10-self-report.md` 末尾加「R1」小节）。

## 禁止事项

- 不改后端任何文件、不改 `vite.config.js`、不引新依赖。
- 不做真实 API 调用测试（浏览器实测由大统领验收）。
- 不自动合并/推送/打 tag；提交到分支 `task/t-s1.10-upload-stuck-board`（续用本卡分支），
  commit message 前缀 `[T-S1.10-R1]`。
