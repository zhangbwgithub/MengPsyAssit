# Task T-S1.2: 修复气泡居中回归——清理空串容错 + 未判定兜底布局 + jobs 时间戳

## 背景与契约

陛下实测反馈（`docs/feedback.md` FB-002，已合 main）：

1. **气泡全居中了，要恢复原来的布局**——根因：陛下上传的真实音频（会话19，59 段）清理阶段失败 → 角色未判定 → 前端兜底走 `align-center`。失败链：纯语气词段（整段只有"嗯……"）被 LLM 清理成空字符串 → `_apply_clean_result` 校验 `text 缺失或非字符串` 抛错 → 重试 2 次（每次 ~2.5 分钟）仍失败 → session failed。
2. **清理/记录阶段太慢**——陛下指示**不做 provider 测速、不换 provider**（维持 MIMO）。本卡只做：① 修掉无效重试（根因修复后自然省时）；② jobs 表加时间戳（可观测性，排障不再靠翻日志）。

分支：`task/t-s1.2-bubble-align-fix`（从 main 开）。提交消息：`[T-S1.2] type: 描述`。
**你不 merge、不 push、不打 tag**；交付后在 `docs/handoffs/task-T-S1.2-self-report.md` 写自报。

## 输入与环境事实（已验证）

- 环境命令同 T-S1.1：`.venv/bin/python`（3.11）、pytest/ruff/npm build、`HOME=/home/houmo` 前缀。
- **失败现场**（会话19，日志实证）：`cleaned[24].text 缺失或非字符串`（第1次）、`cleaned[49].text 缺失或非字符串`（第2次）→ failed。两次失败位置不同，证明是不同语气词段被清理成空串，重试无法自愈。
- `_apply_clean_result`（services.py）当前校验：`cleaned[i].text` 必须是**非空字符串**否则 raise。
- `alignClassOf`（App.vue ~179 行）：role=T 左 / P 右 / **其他居中**——居中分支就是本次回归的视觉来源。
- `jobs` 表（models.py / jobs.py）：列只有 id/type/session_id/provider/status/error，**无时间戳**；`mark_job_running/done/failed`（jobs.py）是写入点。
- `db.py::_heal_missing_columns` 按模型反射对账补列（T-S1.1 已验证对 Segment 新列生效，Job 新列同理）。
- prompt 文件 `app/backend/prompts/clean/v2.md` 可以原地修补（小修，不升版本号；`v1.md` 红线勿动）。
- 现有 33 个单测全绿；`test_clean_bad_json_retries_then_failed` 等用例与本卡改动相关，需同步更新。

## 钉死的决策

1. **空串容错（后端，根因修复）**：`_apply_clean_result` 中 `cleaned[i].text` 为**空字符串**时不再 raise——回退为该段原始 `content`（语气词段原样保留），继续写回。校验仍拒绝：text 缺失、非字符串、seq 不齐、roles 不覆盖。
2. **prompt 双保险**：`clean/v2.md` 清理规则补一条：「若某段只有语气词/填充词（如"嗯……""啊"）而无实质内容，cleaned.text 保留该段原文，禁止输出空字符串。」示例区可补一个语气词段示例。
3. **前端兜底恢复左右布局**：`alignClassOf` 未判定分支改为按代号奇偶交替：`speaker` 字母序号（A=0, B=1…）偶数靠左、奇数靠右（U 等特殊代号视为偶数靠左）。效果：失败/未判定会话恢复对话式左右布局，不再整屏居中。已判定角色仍 T 左 P 右。
4. **jobs 时间戳（仅可观测性）**：`Job` 模型加 `started_at`/`finished_at`（DateTime, nullable）；`mark_job_running` 写 started_at，`mark_job_done`/`mark_job_failed` 写 finished_at（时区处理仿 `store_record` 的 `datetime.now(timezone.utc).replace(tzinfo=None)`）。**不改任何 API 响应**（防镀金）。
5. **不做的事**：不换/不测 LLM provider、不改 record 阶段逻辑、不加前端历史会话入口、不引新依赖。

## 需求（正面清单）

1. 后端：`_apply_clean_result` 空串回退逻辑 + 注释说明（语气词段保留原文）。
2. Prompt：`clean/v2.md` 按决策 2 修补。
3. 前端：`alignClassOf` 按决策 3 改造。
4. 后端：Job 时间戳（决策 4）+ `test_db.py` 补 Job 新列自愈断言（仿 Segment 既有测试）。
5. 测试：
   - 新增：语气词空串回退用例（cleaned 某段 text="" → 该段 cleaned_content=原 content，会话正常 done）；
   - 更新：现有「空 text 导致失败」相关断言（如有）；
   - 新增：Job 时间戳写入断言（mark_job_running/done 后 started_at/finished_at 非空）。
6. 门禁：pytest 全过 + ruff + import 自检 + 前端构建。

## 禁止清单

- 不引新依赖（前后端均不）。
- 不动 `tests/audio/`、`tests/golden/`、`prompts/*/v1.md`、record prompt、provider 实现。
- 不改 GET /sessions 响应结构。
- 不 merge、不 push、不打 tag、不碰 `.env`。
- 不镀金（不加前端新页面/新功能）。

## 验收标准（大统领逐条实测）

1. `.venv/bin/python -m pytest app/backend/tests -q` 全过；`ruff check app/backend` 干净；导入自检过。
2. 语气词空串回退单测过（决策 1）。
3. 前端构建成功；浏览器实测：01 号音频全链路 → 气泡 T 左 P 右、每人一色、无居中（大统领跑）。
4. 会话19 重跑（大统领在修复后执行）：清理成功、角色判定、状态 done——证明真实场景回归修复。
5. Job 时间戳：重跑后 sqlite 查 jobs 表 started_at/finished_at 有值。
6. `alignClassOf` 兜底逻辑代码审查通过（未判定按代号奇偶左右）。
7. 自报在 `docs/handoffs/task-T-S1.2-self-report.md`（逐条 PASS/FAIL/NOT RUN）。

## 技术约束与门禁

- 提交前 `git diff` 自查：只含本卡范围。
- 门禁顺序：构建 → 测试 → 静态 → 前端构建。
- 完成定义 = 验收 1/2/6/7 自测过 + 大统领实测 3/4/5 过。
