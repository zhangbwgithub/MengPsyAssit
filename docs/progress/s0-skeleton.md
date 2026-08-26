# S0 走骨架 — 增量出口报告

> 日期：2026-08-26 · Reasonix 编制 · 分支 `task/t-s0.5-smoke-demo`
> 目标：S0 骨架完成，一键冒烟验证全链路，为 `v0.1-skeleton` tag 提供证据。

## 1. S0 增量一句话总结

**录音 → ASR 转写 → 口语清理 → 客观咨询记录生成**的最薄端到端链路已跑通：上传音频 15 秒内完成全流程，T/P 双色气泡对话稿 + 记录卡片三字段齐全，前端 375px 手机视口不破版。

## 2. 五张任务卡交付物清单

| 任务卡 | 交付物 | 状态 |
|--------|--------|------|
| T-S0.1 治理基线+后端骨架 | `psyapp` 包：7 表 + user_id 隔离 + 统一响应 + 日志掩码 | ✅ 合 main |
| T-S0.2 Provider 抽象层 | paraformer-v2 ASR + qwen-max LLM 接口+单一实现 | ✅ 合 main |
| T-S0.3 最简主链路 | POST/GET /sessions + 状态机 + 后台 pipeline | ✅ 合 main |
| T-S0.4 单页前端 | Vue3+Vite SPA：上传/T/P 着色气泡/记录卡片/375px 适配 | ✅ 合 main |
| T-S0.5 端到端冒烟+演示 | 一键冒烟脚本 + 本报告 + 自报 | 📋 当前卡 |

## 3. 如何 3 分钟复现演示

### 前置条件
- 已安装依赖：`HOME=/home/houmo /home/houmo/.local/bin/uv pip install -p .venv -e "app/backend[dev]"`
- 已安装前端：`cd app/frontend && npm install`
- 环境变量：`DASHSCOPE_API_KEY=你的key`

### 步骤

```bash
# 1. 启动后端（终端 1）
DASHSCOPE_API_KEY=你的key .venv/bin/python -m uvicorn psyapp.main:app --port 8660

# 2. 启动前端（终端 2）
cd app/frontend && npm run build && npm run preview
```

浏览器打开 **http://localhost:5199**

### 预期看到什么

1. **页面加载**：标题「AI 咨询记录助手」+ 合规提示「AI 生成内容仅供专业参考」
2. **上传音频**：点击上传区域，选择 `tests/audio/01_normal_dialogue.wav`
3. **处理动画**：显示「转写中…」进度提示
4. **对话稿展示**：
   - T（咨询师）蓝色气泡，P（来访者）灰色气泡
   - 每段含时间戳和说话人标签
5. **记录卡片**：三个字段齐全
   - 📝 **摘要**：本次咨询要点概述
   - 👨‍⚕️ **咨询师工作**：咨询师采取的技术与干预
   - 🗣️ **来访者自述话题**：来访者主动提及的主题
6. **手机视口**：Chrome DevTools 切 375px，布局不破版

### 一键冒烟（全自动验证）

```bash
DASHSCOPE_API_KEY=你的key .venv/bin/bash tests/e2e/smoke_all.sh
```

脚本会自动起前后端、上传三段音频、轮询、断言、输出汇总表。

## 4. 冒烟三段音频实测结果

> ⚠️ 以下数字来自真实运行 `smoke_all.sh`（2026-08-26 09:31:48 UTC），非编造。

| 音频 | 时长 | 状态 | 段数 | 说话人 | 耗时 |
|------|------|------|------|--------|------|
| `01_normal_dialogue.wav` | 43.4s | done | 11 | P+T | 15s |
| `02_overlap_interruption.wav` | 18.7s | done | 6 | P+T | 10s |
| `03_long_pauses.wav` | 41.6s | done | 8 | P+T | 15s |

**断言全通过**：每段 segments≥5 且含 T/P 两种 speaker，cleaned_text 非空，record 含 summary + counselor_work。`/api/health` 经前端代理 5199 可达。

**结果落盘**：`tests/e2e/results/smoke_all_20260826_093148/`（含 3 段 upload/final JSON + summary.txt）

## 5. 已知限制（S0 故意不做）

以下功能在 S0 范围外，留待后续阶段：

| # | 限制项 | 说明 |
|---|--------|------|
| 1 | 多用户认证 | S0 仅 dev 单用户（dev_user_id=1），无登录/鉴权 |
| 2 | 客户管理 | client_id 固定为 NULL，无客户档案 CRUD |
| 3 | 会话编辑/删除 | 只读查询，无 PATCH/DELETE 接口 |
| 4 | 记录导出 | 无 PDF/Word 导出，仅页面展示 |
| 5 | 实时转写 | 上传后后台异步处理，无 WebSocket 推送 |
| 6 | 多 ASR/LLM 切换 | 接口已抽象但仅 paraformer-v2 + qwen-max 实现 |
| 7 | 数据持久化保障 | SQLite 单文件，无备份/迁移（alembic）|
| 8 | 部署 | 仅本地 dev 模式，无 Docker/CI/CD |
| 9 | 音频格式限制 | 仅支持 .wav/.mp3/.m4a，无格式转换 |
| 10 | 并发控制 | 无任务队列（Celery），BackgroundTasks 串行 |

## 6. 证据清单

| 证据 | 路径 |
|------|------|
| 一键冒烟脚本 | `tests/e2e/smoke_all.sh` |
| 冒烟结果（三段音频完整往返） | `tests/e2e/results/smoke_all_<时间戳>/` |
| 后端链路冒烟（原有） | `tests/e2e/smoke_main_chain.py` |
| 前端冒烟（原有） | `tests/e2e/smoke_frontend.sh` |
| 合成测试音频 | `tests/audio/0{1,2,3}_*.wav` |
| 本报告 | `docs/progress/s0-skeleton.md` |
| 自报 | `docs/handoffs/task-T-S0.5-self-report.md` |
