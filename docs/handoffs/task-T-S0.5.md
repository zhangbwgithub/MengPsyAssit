# 任务卡 T-S0.5：端到端冒烟 + 演示说明（S0 走骨架 · 第 5 张卡 · 增量出口）

## 背景与契约

项目「咨询记录助手」S0 走骨架增量来到最后一张卡。前四张已交付并在 main 分支：
- T-S0.1 后端骨架（`psyapp` 包，FastAPI+SQLAlchemy，7 表带 user_id，含 SQLite 列补齐自愈）
- T-S0.2 Provider 抽象层（paraformer-v2 ASR + qwen-max LLM）
- T-S0.3 最简主链路（上传→转写→清理→记录→查询，状态机）
- T-S0.4 单页前端（Vue3+Vite，T/P 着色对话稿+记录卡片）

本任务：**不写新功能**，把整条链路做成可重复执行的一键冒烟 + 给陛下看的演示说明。这是增量出口卡——做完打 tag `v0.1-skeleton`（由编排方打，你不打）。

仓库根：/home/houmo/meng/MengPsyAssit。先读 `AGENTS.md`。

## 输入与环境事实（已核实）

- 后端：`DASHSCOPE_API_KEY=*** .venv/bin/python -m uvicorn psyapp.main:app --port 8660`
- 前端：`cd app/frontend && npm run build && npm run preview`（5199，带 /api 代理到 8660）
- 已有分步冒烟可参考（勿破坏）：`tests/e2e/smoke_main_chain.py`（后端链路）、`tests/e2e/smoke_frontend.sh`（前端+代理）
- 合成音频：`tests/audio/0{1,2,3}_*.wav`（43.4/18.7/41.6s）
- 已有浏览器验收结论（编排方已实测，供你写演示说明时引用）：真浏览器上传 01 号音频 15 秒走完，11 段 T6/P5 双色气泡，记录卡片三字段齐全，零 JS 错误，375px 手机视口不破版

## 要求

### 1. 一键全链路冒烟 `tests/e2e/smoke_all.sh`（核心交付）

- 一键完成：起后端（8660）→ `npm run build`（若 dist 缺失）→ 起前端 preview（5199）→ 依次用**三段合成音频**全部走 `POST /sessions`（间隔串行，避免并发挤 ASR）→ 轮询每段至 done/failed（单段超时 10 分钟）→ 汇总断言：
  - 3 段全部 `done`（任何一段 failed 则脚本退出码非 0 并指明哪段）
  - 每段 `segments ≥ 5` 且含 T 与 P 两种 speaker
  - 每段 `cleaned_text` 非空、`record` 含 summary + counselor_work
  - `GET /api/health` 经前端代理可达（前端服务在场）
- 输出：每段上传响应、最终会话 JSON 落盘 `tests/e2e/results/smoke_all_<时间戳>/`；终端打印汇总表（音频 / 状态 / 段数 / 说话人 / 耗时）；无论成败清理后台进程（trap）
- 结果目录 `git add -f` 入库（这是增量出口证据）

### 2. 演示说明 `docs/progress/s0-skeleton.md`（增量报告）

给编排方转呈陛下用，内容：
- S0 增量一句话总结 + 五张任务卡交付物清单（各一行）
- **如何 3 分钟复现演示**：两条命令起前后端 + 浏览器打开 5199 + 上传哪个音频 + 预期看到什么（逐条列）
- 本次冒烟三段音频的结果表（从第 1 步实测结果填，数字真实）
- 已知限制（S0 故意不做的清单，引任务书）
- ⚠️ 只写实测数字；不许编造耗时/段数

### 3. 执行冒烟并留证

- 真实跑一遍 `smoke_all.sh`，确认退出码 0
- 结果入库

### 反面清单（违反即验收失败）

- ❌ 不改任何后端/前端业务代码（发现 bug 报告，不擅改——除非是冒烟脚本自身）
- ❌ 不新增功能、不动 prompts/、不动 providers/
- ❌ 不并行上传三段音频（挤 ASR 配额，串行）
- ❌ 代码/结果中出现 API key 明文
- ❌ 不打 tag、不合并（编排方操作）
- ❌ 演示说明中出现未经实测的数字

## 验收标准（编排方逐条实测）

1. `smoke_all.sh` 编排方亲自跑一遍：退出码 0，三段音频全 done，汇总表真实
2. `tests/e2e/results/smoke_all_<时间戳>/` 入库且含三段完整往返
3. `docs/progress/s0-skeleton.md` 存在，数字与冒烟结果一致（抽查段数/耗时）
4. 原有两个冒烟脚本仍可独立跑（不回归）
5. 零密钥泄露
6. git：分支 `task/t-s0.5-smoke-demo`，提交前缀 `[T-S0.5]`

## 技术约束

- 一切用 `.venv/bin/python` / `npm`；启动注入 `DASHSCOPE_API_KEY`
- bash 脚本 `set -euo pipefail`（注意后台进程清理与管道退出码）
- 交付后在 `docs/handoffs/task-T-S0.5-self-report.md` 留自报——自报不作数，编排方实测为准
