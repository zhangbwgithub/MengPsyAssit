# Task T-S1.9: 称呼语校正从「全篇翻转」改为「局部改标」——T-S1.8 误伤修复

## 背景与实证（大统领验收 T-S1.8 时实测证伪，勿复现）

T-S1.8 上线的 `fix_role_flip_by_address`（全篇翻转铁律）在生产实测中**误伤**：

- 会话45（05 号对抗音频，temperature=0 + v2 prompt）模型原始输出（存于 `sessions.raw_transcript`，校正前）：**仅开头 2-8 轮角色翻转，其余约 40 轮与黄金稿一致**。原始稿直接评分 20/26 = 76.9%。
- 铁律看到第 2 轮「咨询师：雨生老师，…」即触发全篇对调，把本来正确的后 40 轮全部打翻 → 最终 6/26 = 23.1%，**比无兜底更差**。
- 会话44（同音频）原始稿同为「仅开头翻转」模式；会话42 无翻转（铁律未触发，无损）。
- 根因：v2 prompt 下 omni 的错误模式是**开头局部翻转**（v1 prompt 时代才是全篇翻转）。「单点称呼证据 ⇒ 全篇翻转」假设证伪，属过度矫正。
- 离线模拟正解（大统领已验证）：只把命中的那一轮「咨询师」就地改标「来访者」、其余轮次一律不动 → 会话44/45 原始稿均达 21/26 = 80.8%。

## 契约（只改一个函数的语义 + 测试）

1. `app/backend/src/psyapp/providers/omni.py`
   - `fix_role_flip_by_address(turns)` 改为**局部改标**：遍历 `(role_label, content)` 列表，凡 `role_label == "咨询师"` 且 `_ADDRESS_FLIP_RE.match(content)` 命中的轮次，把该轮角色改为「来访者」；**其他轮次一律不动，不做全篇对调**。函数名可保留（语义变了，docstring 必须重写说明：称呼对方为「X老师」的人不可能是老师本人，故该轮说话人应是来访者）。`_ADDRESS_FLIP_RE` 与 `temperature: 0.0` 保留不动。
   - `parse_omni_transcript` 的两遍化调用方式不变。
2. `app/backend/tests/test_omni_mode.py` 相应更新（全部离线，不碰真实 API）：
   - 改写触发测试：「咨询师」轮以「雨生老师，…」开头 → **仅该轮**变 来访者/role=P，其余「咨询师」轮**保持**咨询师；断言不再有全篇对调。
   - 保留不触发测试：来访者称呼老师（零变化）、正文提及非句首称呼（零变化）、未命中返回原列表（零副作用）。
   - 新增一条「命中 2 轮」测试：两个「咨询师」轮都以「X老师，」开头 → 两轮都改标来访者，其余不动。
   - `body["temperature"] == 0.0` 断言保留。
3. 自报落 `docs/handoffs/task-T-S1.9-self-report.md`（做了什么/跑了什么命令/逐条对照验收标准/备注），并提交进本卡分支。

## 验收标准（Reasonix 自测必须全过并贴证据）

- `.venv/bin/python -c "import psyapp.main"` 无输出通过
- `.venv/bin/python -m pytest app/backend/tests -q` 全过（基线 58，更新/新增测试后数量自报）
- `.venv/bin/ruff check app/backend` → All checks passed
- `git diff` 自查：只含 `omni.py` + `test_omni_mode.py` + 自报，无越界

## 禁止事项

- 不改 `OMNI_TRANSCRIBE_PROMPT` 常量、不改请求体其余字段、不改 asr 路径、不改 services/routes/前端、不引新依赖、不加日志落库、不加配置开关。
- 不做真实 API 调用（05/01 音频实测由大统领验收）。
- 不自动合并/推送/打 tag；提交到分支 `task/t-s1.9-omni-local-fix`，commit message 前缀 `[T-S1.9]`。
- `tests/audio/` 下的音频与标注是既有未跟踪文件，不要纳入提交。
