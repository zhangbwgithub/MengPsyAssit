# 任务卡 T-S0.4-R2：记录卡片「其他信息」渲染优化（JSON 裸奔问题）

## 问题（陛下看截图指出）

记录卡片的「其他信息」板块直接 `JSON.stringify(basic_info, null, 2)` 贴原始 JSON——陛下看到的是代码块而非可读信息。`basic_info` 里是技术元数据（provider/model/prompt_version/session_id/client_reported_topics），不该以 JSON 原文呈现给使用者。

## 修复要求（只改 `app/frontend/src/App.vue` 该板块，不扩范围）

1. 删掉 `<pre>{{ JSON.stringify(...) }}</pre>` 那段，把「其他信息」改成**人类可读的一行式元信息**：
   - 显示：`模型：qwen-max · 提示词版本：v1 · 会话编号：#<session_id>`（从 basic_info 的 model / prompt_version / session_id 字段取，缺哪个省哪个）
   - `client_reported_topics` 已在上面「来访者话题」渲染过，这里**不重复**显示
   - 样式：小字灰色（`.meta-info` 之类），低调不抢眼
2. `npm run build` 零错误
3. 重跑 `tests/e2e/smoke_frontend.sh` 确认仍 PASS（结果目录入库 `git add -f`）
4. 分支：从当前 main HEAD 开 `task/t-s0.4-r2-record-meta`；提交前缀 `[T-S0.4] fix:`；不合并、不打 tag、不切到其他分支

## 反面清单

- ❌ 不改后端；不动其他板块（概述/咨询师的工作/来访者话题保持原样）
- ❌ 不引组件库

## 验收（编排方真实浏览器实测）

1. 页面记录卡片无 JSON 代码块，「其他信息」为一行可读元信息
2. 冒烟退出码 0
