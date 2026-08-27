# Task T-S1.4: 修复长转写 seq 数错导致清理失败——输入显式编号

## 背景与契约

陛下实测发现「处理失败」（会话25，56 段真实音频）：`source_seqs 未覆盖全部输入段落（期望 [0..55]，实际 [0..56]）`——clean v3 输入只给 `代号: 文本` 逐行稿、让 LLM 自己数行号当 seq，长文本下模型多数出一个虚构序号，两次尝试均被校验拒绝 → 会话 failed。

分支：`task/t-s1.4-explicit-seq`（从 main 开）。提交消息：`[T-S1.4] type: 描述`。
**你不 merge、不 push、不打 tag**；自报写 `docs/handoffs/task-T-S1.4-self-report.md`。

## 输入与环境事实（已验证）

- 环境同前卡（.venv/pytest/ruff/npm build，HOME=/home/houmo）。
- 现状输入构造：`segments.py::build_transcript_lines_from_segments` → `代号: 文本` 逐行。
- `clean/v3.md` 输入格式节写「每行的行号（从 0 开始）就是该段的 seq」——**数行号是失败根因**。
- `validate_clean_result`（services.py）：source_seqs 拼接后必须恰好 0..n-1——此校验保留（安全网），只修输入侧。
- 失败会话25 音频在 `data/audio/6533ba090a21421081e266833276ff33.mp3`（56 段）——大统领验收时重跑。

## 钉死的决策

1. **输入显式编号（根因修复）**：转写稿每行格式改为 `[seq] 代号: 文本`，如：
   ```
   [0] A: 你好，请坐。这一周过得怎么样？
   [1] B: 嗯……就是，最近压力很大。
   ```
   `build_transcript_lines_from_segments` 输出带编号；**分块路径每块内也带全局 seq 编号**（不是块内从 0 重数——保持与输出 source_seqs 的全局口径一致；检查现有分块拼块逻辑并同步）。
2. **clean/v3.md 同步**：输入格式节改为「每行格式 `[seq] 代号: 文本`，方括号内即该段 seq，source_seqs 必须逐字引用这些编号，不得自创、不得数行号」；示例区同步带编号。
3. **校验不动**：`validate_clean_result` 严格规则保留（这是安全网）；不放宽覆盖校验。
4. 测试：现有单测的 fake transcript 输入同步更新；新增 1 个断言：输入文本含 `[0]`/`[1]`… 显式编号（防回归）。

## 禁止清单

- 不改校验逻辑、不改段落重组逻辑、不动 v1/v2/record prompt、不动 provider、不引依赖。
- 不 merge、不 push、不打 tag、不碰 `.env`。

## 验收标准（大统领逐条实测）

1. pytest 全过 + ruff + 导入自检 + 前端构建（前端不受影响也须构建确认）。
2. 单测断言输入显式编号。
3. **陛下失败音频重跑**（大统领执行，56 段）：清理成功、会话 done、段落重组正常。
4. 自报在 `docs/handoffs/task-T-S1.4-self-report.md`。

## 门禁

构建 → 测试 → 静态 → 前端构建；提交前 `git diff` 自查只含本卡范围。
