# 任务卡 T-S0.4-R1：微修复——免责声明重复渲染

## 问题（编排方真实浏览器验收 + 视觉审查发现）

`app/frontend/index.html` 第 10 行有一个静态 `<p class="disclaimer">AI 生成内容仅供专业参考</p>`，同时 `App.vue` 页脚也渲染同一句——真实页面上出现**两份免责声明**（页脚一份 + #app 外游离一份，后者左对齐贴边，观感突兀）。

## 修复要求（只此一处，不扩范围）

1. 删除 `app/frontend/index.html` 中第 10 行那句 `<p class="disclaimer">...`（保留 App.vue 页脚的版本——它在 Vue 应用内，是正式渲染路径；index.html 的静态版只在 JS 加载失败时才有意义，而那种场景下应用本身也不可用）
2. `npm run build` 零错误
3. 重跑 `tests/e2e/smoke_frontend.sh`（确认仍 PASS——注意：冒烟断言检查的是页面含该文案，App.vue 的页脚文案在 SPA 里是 JS 渲染的，若冒烟的 grep 检查因此失败，说明冒烟检查的是静态 HTML——此时把冒烟断言改为检查构建产物/或说明情况并保留 index.html 的 noscript 兜底写法 `<noscript><p>AI 生成内容仅供专业参考</p></noscript>`，二选一，注释说明理由）
4. 提交：分支继续 `task/t-s0.4-frontend`，前缀 `[T-S0.4] fix:`，把本次冒烟新结果目录一并 `git add -f` 入库（`tests/e2e/results/frontend_20260826_091917/`，编排方验收时产生）
5. 不合并、不打 tag

## 验收（编排方实测）

1. 页面渲染后声明文案只出现一次（DOM 查询计数）
2. 冒烟脚本退出码 0
3. ruff/pytest 不涉及（纯前端改动）
