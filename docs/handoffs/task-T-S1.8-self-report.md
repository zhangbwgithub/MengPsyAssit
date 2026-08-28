# T-S1.8 自报：称呼语翻转校正——omni 角色判定确定性兜底

## 做了什么

1. `app/backend/src/psyapp/providers/omni.py`
   - `QwenOmniLLM.transcribe_audio()` 请求体加 `"temperature": 0.0`（与 `modalities`、`enable_thinking` 同级）。
   - 新增确定性规则 `fix_role_flip_by_address(turns) -> turns`：
     - 扫描任意「咨询师」轮，内容匹配 `_ADDRESS_FLIP_RE`（`^X老师` + 标点开头，X 为 1-6 个中英文字符）→ 判定全篇翻转。
     - 把全部轮次「咨询师」↔「来访者」互换，其余角色标签不动；只翻一次；未命中零副作用（原样返回）。
   - `parse_omni_transcript()` 调整为两遍：先逐行解析出 `(role_label, content)` 中间列表，调用校正函数后，再做角色映射与 speaker 代号分配。翻转后的 role / role_label / speaker 全部基于校正后的角色。
2. `app/backend/tests/test_omni_mode.py` 追加 4 项测试（全部离线，无真实 API）：
   - 翻转触发：「咨询师」轮以「雨生老师，…」开头 → role 变 P/来访者，原「来访者」轮变 T/咨询师，speaker 代号随校正后的角色分配。
   - 不触发（常规对话）：「来访者」轮以「王老师，我最近睡不好」开头 → 零变化。
   - 不触发（正文提及非称呼）：「咨询师」轮「你刚才提到老师说的那句话」→ 零变化。
   - `fix_role_flip_by_address` 未命中时返回同一列表（零副作用）。
   - 现有请求结构测试补断言 `body["temperature"] == 0.0`。
3. `docs/handoffs/task-T-S1.8-self-report.md`（本文件）。

## 跑了什么命令 / 结果

- 导入自检：`.venv/bin/python -c "import psyapp.main"` → 通过（无输出）。
- 测试：`.venv/bin/python -m pytest app/backend/tests -q` → **58 passed**（改动前基线 54，新增 4 项），全部离线不碰真实 API。
- 静态：`.venv/bin/ruff check app/backend` → **All checks passed!**。

## 逐条对照验收标准

| 项 | 结果 | 说明 |
| -- | -- | -- |
| pytest 全过 + ruff + 导入自检 | PASS | 58 passed / All checks passed / import 正常 |
| 前端构建 | NOT RUN | 本卡只动后端 omni provider 与后端测试，未改前端代码；前端构建留大统领实测 |
| 05 号对抗音频实测（开头零翻转、≥77%） | NOT RUN | 依赖真实 DashScope API + 05 号音频，属大统领实测范围 |
| 01 号常规音频回归（不误触发） | NOT RUN | 依赖真实 API + 01 号音频，属大统领实测范围；离线测试已覆盖「来访者称呼老师」不误触发分支 |
| 自报落位 | PASS | `docs/handoffs/task-T-S1.8-self-report.md` |

## 备注

- 未改 prompt 常量、asr 路径、`.env`；未引新依赖；未做配置开关/日志落库。
- 提交前 `git diff` 自查：只含 `omni.py` + `test_omni_mode.py` 本卡范围，无残留。
- `tests/audio/` 下 04/05/06 音频与标注文件为工作区既有未跟踪文件，不在本卡范围内，未纳入提交。
