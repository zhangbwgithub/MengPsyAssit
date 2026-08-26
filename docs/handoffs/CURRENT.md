# CURRENT.md — 跨会话交接台账

> 工作流 §6：增量收尾及会话压缩前必答四问。最后更新：2026-08-26 大统领

## 当前状态：S0 走骨架进行中

| 任务 | 状态 | 证据 |
|------|------|------|
| T-S0.1 治理基线+后端骨架 | ✅ 完成已合 main | merge 3d87231（--no-ff）；验收 8/8 实测 PASS |
| T-S0.2 Provider 接口+单一实现 | 📋 任务卡已锻造，派 k3 执行中 | docs/handoffs/task-T-S0.2.md，分支 task/t-s0.2-providers |
| T-S0.3 最简主链路 API | ⏳ 待 T-S0.2 | — |
| T-S0.4 单页前端 | ⏳ 待 T-S0.3 | — |
| T-S0.5 端到端冒烟+演示 | ⏳ 待 T-S0.4 | 出口 tag `v0.1-skeleton` |

## 边界变了什么

- S0 开工：后端包 `psyapp` 立起（app/backend/src 布局，pyproject + uv 可编辑安装进项目 .venv）
- 数据模型第一天带 user_id（7 表全按方案 §5，dev 单用户播种 username=dev）
- 统一响应 `{ok, data|error}` + ApiError 体系 + 日志 sk- 掩码过滤
- AGENTS.md 成为仓库工作规则单一入口（分支/提交/红线/门禁/环境事实）
- .env 由编排方管理：Reasonix 会话不新建 .env，需要 DASHSCOPE_API_KEY 时由大统领派单命令注入环境变量

## 证据是什么

- T-S0.1 验收全实测：`/health` 200 返回 `{"status":"ok","app":"psy-backend","env":"dev"}`；404 返回 `{ok:false,error:{code:not_found}}`；pytest 4 passed；ruff All checks passed；sqlite 反射 7 表且 clients/sessions/segments/records 均含 user_id；git grep 无 sk- 明文
- 依赖：.venv 已装 fastapi/uvicorn/sqlalchemy/pydantic-settings/pytest/httpx/ruff（`uv pip install -p .venv -e "app/backend[dev]"`）

## 什么没验证

- Provider 真实调用（T-S0.2 验收时实测）
- 主链路端到端（T-S0.3~S0.5）

## 如何回滚

- T-S0.1 整体回滚：`git revert -m 1 3d87231`；分支 `task/t-s0.1-backend-skeleton` 保留备查
- 后续任务同样按任务 ID 提交、按分支隔离，单任务回滚不影响其他

## 环境备忘

- 项目 venv：.venv/（dashscope + fastapi 栈）；评测/运行一律 .venv/bin/python
- DASHSCOPE_API_KEY 在 ~/.hermes/profiles/qqbot/.env；派单时由大统领注入环境变量，Reasonix 代码只读 env
- reasonix 姿势：绝对路径 /home/houmo/.hermes/node/bin/reasonix + `HOME=/home/houmo` + `--permission-mode bypassPermissions --dir <仓库根>` + `--max-steps 80`
- GOTCHAS（P0 沉淀，S0 实现必读）：paraformer 走 HTTP 路径 + `X-DashScope-OssResourceResolve: enable` 头（勿用 SDK 传临时 URL）；参考实现 `tests/asr_eval/providers/paraformer.py`
