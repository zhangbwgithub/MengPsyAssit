# T-S1.9 自报：称呼语校正从「全篇翻转」改为「局部改标」——T-S1.8 误伤修复

## 做了什么

1. `app/backend/src/psyapp/providers/omni.py`
   - `fix_role_flip_by_address(turns)` 语义从「命中即全篇对调」改为「局部改标」：遍历 `(role_label, content)` 列表，凡 `role_label == "咨询师"` 且 `_ADDRESS_FLIP_RE.match(content)` 命中的轮次，仅把该轮角色改为「来访者」；其余轮次（包括其他「咨询师」「来访者」轮）一律不动，不再做全篇「咨询师」↔「来访者」互换。
   - 函数名保留；docstring 重写，说明「称呼对方为『X老师』的人不可能是老师本人，故该轮说话人应是来访者」。
   - `_ADDRESS_FLIP_RE` 与 `temperature: 0.0` 保留不动；`parse_omni_transcript` 的两遍化调用方式不变。

2. `app/backend/tests/test_omni_mode.py` 相应更新（全部离线，不碰真实 API）：
   - 改写触发测试：仅命中的「咨询师」轮变来访者/P，其余「咨询师」「来访者」轮保持原标，断言不再有全篇对调。
   - 保留不触发测试：来访者称呼老师（零变化）、正文提及非句首称呼（零变化）、未命中返回原列表（零副作用）。
   - 新增「命中 2 轮」测试：两个「咨询师」轮均以「X老师，」开头 → 两轮都改标来访者，其余不动。
   - 保留 `body["temperature"] == 0.0` 断言。

3. `docs/handoffs/task-T-S1.9-self-report.md`（本文件）。

## 跑了什么命令 / 结果

- 导入自检：`.venv/bin/python -c "import psyapp.main"` → 通过（无输出）。
- 测试：`.venv/bin/python -m pytest app/backend/tests -q` → **59 passed**（基线 58，改写 1 项 + 新增 1 项），全部离线不碰真实 API。
- 静态：`.venv/bin/ruff check app/backend` → **All checks passed!**。

## 逐条对照验收标准

| 项 | 结果 | 说明 |
| -- | -- | -- |
| 导入自检 | PASS | `.venv/bin/python -c "import psyapp.main"` 无输出通过 |
| pytest 全过 | PASS | 59 passed（自报数量，基线 58） |
| ruff | PASS | All checks passed! |
| git diff 只含本卡文件 | PASS | 只含 `omni.py` + `test_omni_mode.py` + 本自报，无越界 |
| 05/01 音频实测 | NOT RUN | 依赖真实 DashScope API + 测试音频，属大统领实测；本卡未做真实 API 调用 |

## 备注

- 未改 `OMNI_TRANSCRIBE_PROMPT` 常量、请求体其余字段、asr 路径、services/routes/前端；未引新依赖；未加日志落库；未加配置开关。
- `tests/audio/` 下 04/05/06 音频与标注文件为工作区既有未跟踪文件，不在本卡范围内，未纳入提交。
- 提交到分支 `task/t-s1.9-omni-local-fix`，commit message 前缀 `[T-S1.9]`。
