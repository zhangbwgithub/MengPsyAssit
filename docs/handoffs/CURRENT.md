# CURRENT.md — 跨会话交接台账

> 工作流 §6：增量收尾及会话压缩前必答四问。最后更新：2026-08-27 大统领

## 当前状态：S1 进行中——T-S1.1 角色分离重构 ✅ 合 main（2026-08-27），反馈台账运行中

### 进行中
- （无进行中任务卡）

### 已完成（S1）
- **T-S1.1 角色分离重构** ✅：转写代号制（去掉 speaker_zero）+ clean 阶段 LLM 角色判定（T/P、同角色多人 ABC）+ 前端每人一色气泡（T 左/P 右，6 色调色板）。merge `9e2384c`；大统领实测：33 pytest + ruff + 端到端 2 音频（01/02 号，角色判定全对）+ headless Chrome 浏览器复验（含 375px）全过。自报 `docs/handoffs/task-T-S1.1-self-report.md`。
- **反馈台账**：`docs/feedback.md` 建立，陛下反馈逐条记录（FB-001 三条已录，全部落实：1/2 由 T-S1.1 交付，3 调研无现成件暂缓）。

### 关键决策（2026-08-27）
- paraformer-v2 无性别信息 → 代号用「说话人 A/B」，不用 男A/女A（陛下已认可偏差）。
- 精神动力学记录风格：GitHub 调研无现成可用 plugin/skill（候选均不匹配，详见反馈台账），按陛下指示暂缓，未来经 plugin/skill 机制接入；record 风格本期不动。
- 演示系统已固化为 systemd 用户服务：mengpsy-backend(:8660) + mengpsy-frontend(:5199)，2026-08-27 端到端浏览器验收通过。

## 上一阶段：S0 走骨架 ✅ 收官（tag `v0.1-skeleton`）

| 任务 | 状态 | 证据 |
|------|------|------|
| T-S0.1 治理基线+后端骨架 | ✅ | merge 3d87231，验收 8/8 |
| T-S0.2 Provider 接口 | ✅ | merge b668783，验收 7/7（真实冒烟在案） |
| T-S0.3 最简主链路 | ✅ | merge d2f41e1；R1 修 schema 漂移（旧库列自愈），复验原始故障场景通过 |
| T-S0.4 单页前端 | ✅ | merge 4b9b872；真实浏览器验收（真上传 15s 端到端，0 JS 错误，375px 不破版）；R1 修声明重复渲染 |
| T-S0.5 冒烟+演示 | ✅ | merge f2f249a + tag v0.1-skeleton；smoke_all 3/3 全过，编排方独立复跑数字与自报一致 |

## 边界变了什么

- 后端完整主链路：`POST /sessions`（≤200MB、随机文件名、扩展名白名单）→ BackgroundTasks 串行「转写→清理→记录」→ `GET /sessions/{id}`（segments/cleaned_text/record）→ 状态机 uploading→transcribing→done/failed
- Provider 抽象定型：`ASRProvider.transcribe/health_check`、`LLMProvider.complete/health_check`；paraformer-v2（纯 HTTP + OssResourceResolve 头 + oss.upload 子进程）+ qwen-max（compatible-mode）
- SQLite dev 期列自愈：`init_db()` 后 `PRAGMA` 对账缺列 `ALTER TABLE ADD COLUMN`（db.py `_heal_missing_columns`）——以后加列不炸旧库
- 前端：app/frontend/ Vue3+Vite SPA（无路由无 Pinia），`/api` 代理 dev+preview 双配置，`VITE_API_BASE` 可覆盖
- 冒烟三件套：`smoke_main_chain.py`（后端）/ `smoke_frontend.sh`（前端）/ `smoke_all.sh`（一键三段音频全链路，隔离 DB+DATA_DIR）
- e2e 结果入库规则：JSON/日志/summary 入库（.log 需 -f），**audio_store/ 与 smoke.db 运行时二进制已加 .gitignore 排除**

## 证据是什么

- 一键冒烟 `tests/e2e/smoke_all.sh` 两次独立运行全过（mimo 自跑 + 编排方复跑）：三段音频 11/6/8 段、T+P 双说话人、15s/10s/15s——两次数字一致
- 真实浏览器（headless Chrome CDP）：上传→状态轮播→done 渲染，截图在 /tmp/ts04_verify/；声明文案渲染一次（R1 后）
- 后端 24 passed + ruff All checks passed（main HEAD）
- 演示说明：docs/progress/s0-skeleton.md（含 3 分钟复现步骤，数字已核对为实测）

## 什么没验证

- 未向陛下真人演示（等本条消息后安排）
- 打断重叠场景转写质量仅看段数/说话人，未逐句对照黄金稿（S2 编辑增量关注）
- 长音频（180 分钟）未实测，只验 ≤43s（S1 分片上传时覆盖）
- 多会话并发未测（BackgroundTasks 串行，S0 单机单用户够用）

## 增补：04 号真实音频实测（2026-08-26 晚）

- 陛下提供 `xhs_audio.mp3`（5.5min/4.0MB）已入库 `tests/audio/04_xhs_audio.mp3`（.gitignore 放行 `!tests/audio/*.mp3`）
- 全链路实测：上传→75s done，59 段；**说话人映射需选 `speaker_zero=P`**（该音频说话人 0 是来访者，默认 T 会反）——前端有单选开关，已验证两种映射均可切换
- paraformer 分离小错位 1 处（#46 句被拦腰拆），正是 S2 说话人映射编辑的设计场景，S0 不修
- T-S0.4-R2：记录卡片「其他信息」从 JSON 裸奔改为一行可读元信息（模型/提示词版本/会话编号），陛下指出+真实浏览器复验通过，合 main c727fa3

## 如何回滚

- 增量整体回滚：`git revert` 各任务 merge 提交（均 --no-ff）；tag 可 `git tag -d v0.1-skeleton && git push origin :refs/tags/v0.1-skeleton`
- 运行时数据：`data/`（gitignore，可随时重建，init_db 幂等+播种）

## 环境备忘

- 后端：`DASHSCOPE_API_KEY=*** .venv/bin/python -m uvicorn psyapp.main:app --port 8660`
- 前端：`cd app/frontend && npm run build && npm run preview`（5199）→ http://localhost:5199
- Reasonix 派单脚本模板：/home/houmo/meng/dispatch_ts0*.sh（key 从 ~/.hermes/profiles/qqbot/.env 提取注入）
- 浏览器验收脚本：/home/houmo/meng/verify_ts04_browser.py（CDP headless Chrome）
- GOTCHAS 更新：`create_all()` 不 ALTER 旧表（已用列自愈兜底）；vite preview 代理需显式配置（已配）；e2e 结果目录别塞运行时二进制
