# Task T-S1.7 自报：OMNI_TRANSCRIBE_PROMPT 升 v2——称呼语铁证锚定（修复角色翻转缺陷）

## 做了什么

仅改一处常量：`app/backend/src/psyapp/providers/omni.py` 中 `OMNI_TRANSCRIBE_PROMPT` 整段替换为 FB-009 陛下拍板的 v2 原文（照抄未改写），并把常量上方注释改为「转写+清洗 prompt v2（FB-009 陛下拍板升级，称呼语铁证锚定修复角色翻转；照抄勿改写）」。

v2 相对 v1 的关键变化（均为原文内容，非自行发挥）：
- 第 1 条改为「角色判定铁律」：a) 称呼语优先（称对方「某某老师」则说话人不是该老师本人）、b) 不假设「提问者=咨询师」（存在来访者强势追问）、c) 全篇角色一致性并复核翻转。
- 第 3 条新增「修正重复字（如「是是」→「是」）」。
- 第 4 条新增「笑声、叹气等非语言信息用（笑）等形式保留」。
- 第 5 条输出格式保持不变（轮次号\t角色\t内容），其中的 `\t` 为真实制表符（与 v1 一致，非反斜杠字面量）。

其他一切未动：`parse_omni_transcript()` 解析逻辑、请求体结构（modalities/enable_thinking=false）、services/routes/前端、asr 路径均未碰；未引新依赖、未动 `.env`、未新建测试音频/黄金稿。`tests/test_omni_mode.py` 仅引用 `OMNI_TRANSCRIBE_PROMPT`（无对其内容的「照抄探针」子串断言），故无需同步更新断言，也未新增测试。

## 跑了什么命令 / 结果

| 命令 | 结果 |
|---|---|
| `HOME=/home/houmo uv pip install -p .venv -e "app/backend[dev]"` | **PASS**（Built + Installed psyapp 0.1.0） |
| `HOME=/home/houmo .venv/bin/python -c "import psyapp.main; print('import ok')"` | **PASS**（import ok） |
| `HOME=/home/houmo .venv/bin/python -m pytest app/backend/tests -q` | **PASS：54 passed in 12.07s** |
| `HOME=/home/houmo .venv/bin/ruff check app/backend` | **PASS：All checks passed!** |
| `cd app/frontend && HOME=/home/houmo npm run build` | **PASS**（vite build，390ms） |
| prompt 字面量校验（脚本检查） | **PASS**：含真实制表符、无 `\\t` 反斜杠字面量；共 9 行，逐行与 v2 原文一致 |

## 逐条对照验收标准

1. pytest 全过 + ruff + 导入自检 + 前端构建：**PASS**（54 passed / All checks passed / import ok / vite build ok）。
2. 05 号对抗音频实测（角色标注对照黄金稿 ≥80%，基线 24%）：**NOT RUN**（大统领执行；本卡已按钉死原文落地线上 v2 prompt，此前大统领先导实证增强版两次复跑稳定 81%）。
3. 01 号合成音频 omni 模式回归：**NOT RUN**（大统领执行；后端 54 项测试全部通过，含 omni 解析/请求结构/重试用例）。
4. 自报在 `docs/handoffs/task-T-S1.7-self-report.md`：**PASS**（本文件）。

## 说明与遗留

- 未 merge、未 push、未打 tag、未碰 `.env`；未改解析逻辑、未加配置开关、未做 prompt 版本化；未把音频 base64 写日志。
- `git diff` 自查范围：仅 `app/backend/src/psyapp/providers/omni.py`（常量 + 上方注释），无其他改动。工作区中 `tests/audio/` 下的未跟踪文件（04/05/06 号音频与黄金稿）为本仓库既有共享测试资产，非本卡新增，未纳入提交。
- 交付证据以大统领实测为准。
