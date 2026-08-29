# CURRENT.md — 跨会话交接台账

> 工作流 §6：增量收尾及会话压缩前必答四问。最后更新：2026-08-27 大统领

## 当前状态：S1 进行中——T-S1.1~S1.10 十一卡连发 ✅ 合 main（2026-08-27~29），双模式管线 + omni prompt v2 + 称呼语局部改标 + 上传挂起防护 + 左侧记录看板上线，反馈台账运行中（FB-001~010）

### 进行中
- （无进行中任务卡）

### 已完成（S1 增补）
- **T-S1.12 记录标签/摘要编辑 + 看板排序筛选/分组/删除 + 深色主题** ✅（merge ca755cc）：FB-011 前端卡（App.vue 独改 +1389 行）。记录卡摘要行（brief 优先、无则截 record.summary 前 100 字）+ 标签徽标行，各带内联编辑（摘要≤100 字校验、标签逗号分隔，调 PATCH 成功刷新看板）；咨询记录整卡折叠/展开。看板：排序下拉（时间/时长/字数/文件名 × 升降序，字数降序实测有序）+ 标签/组筛选 + 按音频折叠开关；分组区增删改查（新建弹层组名/标签/备注、删组确认「记录不会删除」）；条目内分组下拉移入/移出；删除会话确认框（编号+文件名+不可撤销提示）后级联删。深色主题亮/自动/暗三档，localStorage 持久化 + 跟随系统，CSS 变量成体系（实测暗背景 rgb(15,17,21)）。验收：68 pytest + ruff + build 全过；真浏览器 14 项实测全过零 JS 异常。流程瑕疵在案：Reasonix 完工未提交（自报+代码留工作区），大统领补归档提交 4d46b93——后续派单需盯提交环节。
- **T-S1.11 记录元数据富化 + 分组 + 编辑/删除 API** ✅（merge f3227cb）：FB-011 后端卡。模型加列（original_filename/tags/brief/group_id，走列自愈）+ 新表 session_groups；上传存来源文件名 + ffprobe 时长；record prompt 升 v3（客观性铁律不动，加 brief≤100字 + tags 1-4个）；新 API：看板富化查询、PATCH 编辑（brief>100→422、非法组→404）、DELETE 级联（行+音频文件）、/groups CRUD（重名422、删组记录归未分组）。验收：68 pytest + ruff + import 全过；真 API 实测全链——上传「验收测试音频07号.mp3」done 后 tags=['咨询','个体']、brief 58字客观句式、时长78s、字数323 全落库；分组增删改查+编辑+越权拒绝逐项验过；DELETE 后四表清零+音频文件消失。
- **T-S1.10 + R1 上传挂起防护 + 左侧上传/分析记录看板** ✅（merge 16e1af6 / c9ad5eb）：FB-010 陛下报「传完一个再传下一个就卡住」+「服务好像坏了」。大统领诊断：服务未坏（两 systemd 单元持续在线）；卡住铁证=第三发从未到达后端（后端日志零 POST、audio 零残片），根因前端零防护——上传/轮询 fetch 无超时、轮询无在途护栏，网络抖动即挂死吃光连接池。修复（Reasonix，App.vue 独改）：上传 300s + 轮询 10s AbortController 超时、轮询在途护栏、连续 3 败退出报错；左侧 260px 看板（sticky，<768px 落顶）复用 `GET /api/sessions`，条目=#编号+状态徽标+本地时间，点击回看复用现有渲染+自动恢复轮询。R1 修看板时间 UTC 原值→本地时区（`new Date(value+'Z')`）。验收：59 pytest + ruff + build 全过；真浏览器 7 项实测全过（72 条上榜/点击回看/上传即+1 高亮/375px 不破版）+ R1 时区对表实测一致（05:19 UTC→13:19 显示）。

### 已完成（S1）
- **T-S1.9 称呼语校正改局部改标** ✅（3ac297d）：T-S1.8 的「全篇翻转」铁律在大统领实测中误伤（会话45：模型原始稿仅开头翻转、后40轮全对，全篇对调后 77%→23%）——靠 `sessions.raw_transcript` 取证证伪。改为**局部改标**：仅命中的「咨询师」轮（内容以「X老师，」开头）就地改「来访者」，其余不动。大统领实测：门禁 59 pytest + ruff 全过；05号线上实测 80%（20对/5错，开头零翻转，剩余全在 #13/#17-20 歧义区）；离线决定性验证——会话44/45 两份「开头翻转」原始稿走新解析器均修复（第2轮来访者✅）；01号常规回归正常（8轮 4/4，规则零误触发）。
- **T-S1.8 称呼语翻转校正（全篇版）** ⚠️ 已合并但实测证伪，由 T-S1.9 修正：temperature=0.0 保留（无害）；「单点称呼 ⇒ 全篇翻转」假设证伪（v2 prompt 下错误模式是开头局部翻转而非全篇）。教训入台账。
- **T-S1.7 omni prompt 升 v2** ✅：`OMNI_TRANSCRIBE_PROMPT` 换称呼语铁证锚定版（FB-009 陛下拍板）。大统领实测：门禁 54 pytest + ruff + 前端构建全过；**05号对抗音频线上 omni 模式角色正确率 24%→81%（21对/5错，与探针两次复跑完全一致）**，剩余错误集中在 #13/#17-20 内容歧义区（ASR 管线同样错，非 prompt 可解）；01号常规音频回归正常（8轮、角色4/4、记录三字段齐全）。
- **T-S1.6 双模式管线** ✅：`qwen3.5-omni-plus` 多模态直转（默认）+ ASR 管线（paraformer+deepseek，未来实时录音入口）并存；上传可选模式、显式标模型；omni 无时间戳、两阶段进度条。merge `见git log`；大统领实测：54 pytest + 陛下真实音频 omni 实测 5s 出 17 轮（与探针一致）+ 浏览器双模式复验全过（选择器/模型名/进度条/375px）。
- **T-S1.5 + T-S1.5b 清洗/记录模型切换** ✅：clean+record 全链切 `deepseek-v4-flash`（关 thinking、temp 锁 0.2），clean prompt 升 v4（拼音推理链），`clean_llm_*`/`record_llm_*` 独立配置、全局 `llm_provider`(mimo) 保留兜底。merge `25884b9`；大统领实测：46 pytest + 陛下 56 段音频重跑——**clean 294s→8s（37x）、record 48s→3s（16x）、总 352s→21s**，质量不降（她27他0、记录三字段齐全、prompt v4、provider 如实落库）。调研支撑：FB-005（teamtee/CoC/zxkane 蒸馏，skill `asr-transcript-cleanup` 已建）。
- **T-S1.4 显式 seq 编号修复** ✅：clean 输入改 `[seq] 代号: 文本`（分块路径全局口径）+ prompt 明确逐字引用编号。merge `d1b96e0`；大统领实测：40 pytest + 陛下 56 段失败音频重跑 done（44 段重组、她25他0）。注：首次重跑撞阿里云 DashScope 云端瞬时故障（SERVER_ERROR，转写阶段），重试即过——云端偶发故障非代码问题，但暴露「转写阶段无自动重试」短板，可作后续优化候选。
- **T-S1.3 语义重拼清洗** ✅：clean v3 段落重组（碎片合并/上下文纠错他→她/分块>60段/进度条三阶段/转写中间态紧凑气泡）。merge `2eaad76`；大统领实测：39 pytest + 陛下真实音频重跑（59→39 段、她21/他5 语境纠错生效）+ 浏览器进度条/中间态/完成态复验全过。已知局限：个别说话人分离小错位仍残留（ASR 源头问题，S2 编辑增量覆盖）；≤60 段走单次调用（59 段实测 clean 294s，分块提速面向更长会谈）。
- **T-S1.2 气泡居中回归修复** ✅：空串回退原内容 + 未判定奇偶左右布局 + jobs 时间戳。merge `a5b17d8`；陛下失败音频重跑 done。
- **T-S1.1 角色分离重构** ✅：转写代号制（去 speaker_zero）+ clean 阶段 LLM 角色判定 + 每人一色气泡。merge `9e2384c`。
- **反馈台账**：`docs/feedback.md`——FB-001（角色流程三条）/FB-002（气泡回归+耗时）/FB-003（语义重拼+清洗skill调研+进度条）全部落实或记录在案。

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
