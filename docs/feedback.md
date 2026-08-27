# 反馈台账（陛下的修改意见记录）

> 陛下每次反馈逐条记录在此：原文要点 → 处理结论 → 落实去向。由大统领维护，只增不删。

---

## FB-001 · 2026-08-27 · 角色分离流程重构 + 记录风格

### 反馈 1：转写阶段先不定义角色，仅做角色分离，用代号区分（男A/女A/男B…），去掉说话人映射选择框

**结论：✅ 采纳，纳入任务卡 T-S1.1**

- 落实：转写阶段 segments 只存说话人代号（按首次出现顺序 A/B/C…），前端去掉 `speaker_zero` 映射单选，POST /sessions 移除该参数。
- 一处技术偏差说明：paraformer-v2 说话人分离**不返回性别信息**，无法直接给出「男A/女A」式代号。落地为性别中性代号「说话人 A / 说话人 B / …」（如后续接入带性别识别的 ASR 或 LLM 从内容推断出性别，可再升级为 男A/女A 式标签）。

### 反馈 2：清理阶段由 LLM 通过对话内容判定具体角色（咨询师/来访者，同角色多人用 ABC 区分），该阶段显示做成对话气泡、不同人不同颜色

**结论：✅ 采纳，纳入任务卡 T-S1.1**

- 落实：clean 阶段升级为「口语清理 + 角色判定」，LLM 输出结构化 JSON（角色归属 + 逐段清理文本）；segments 表增加 role/role_label/cleaned_content 列。
- 前端：清理后文本从纯段落改为对话气泡渲染；气泡按说话人代号着色（每人一色），咨询师靠左/来访者靠右，标签显示判定后的角色（同角色多人显示 咨询师A/来访者B 式标签）。

### 反馈 3：咨询记录格式要符合精神动力学咨询师的叙述风格；先在 GitHub（deepwiki）找现成 plugin/skill 嵌入，找不到就算了

**结论：🔍 已调研，暂无可用现成件，按陛下指示暂缓（未来经 plugin/skill 机制接入）**

- 调研范围（2026-08-27，大统领实测）：
  - GitHub 仓库搜索：`psychodynamic skill` / `psychodynamic formulation` / `therapy-notes` / `psychotherapy record` / `精神动力学` 等多组关键词
  - anthropics/skills 官方技能仓库、davila7/claude-code-templates（120+ scientific skills，含 clinical-reports/treatment-plans，均为西医临床文书向，无精神动力学叙述风格）
  - GitHub topic 页（ifs-therapy、claude-code-skills 等）
- 最接近的候选（均不匹配，记录备查）：
  | 候选 | 内容 | 不匹配原因 |
  |---|---|---|
  | `luof9924-ones/house-tree-person-psychodynamic-skill` | 房树人绘画的精神动力学解读技能 | 面向绘画投射测验，非咨询记录 |
  | `sethmblack/skill-organizational-psychodynamics-analysis` | 组织心理动力学分析 | 面向组织管理，非临床咨询 |
  | `alirezarezvani/claude-code-skills-factory`（Health SDK Builder） | 德语 PTV 10 医保申请生成，含 psychodynamic formulation | 面向德国医保申报文书，德语、格式固定，非中文咨询记录叙述 |
- 处理：记录生成 prompt 暂维持现有客观记录风格（v1）；待未来陛下的精神动力学风格 plugin/skill 就绪后，经 prompts 模板机制接入（record 模板版本化已支持）。

---

## FB-002 · 2026-08-27 · 气泡布局回退 + 清理/记录阶段太慢

### 反馈 1：转写对话稿气泡都居中了，要恢复原来的布局

**结论：✅ 采纳，纳入任务卡 T-S1.2**

- 根因：陛下上传的真实音频（会话19）清理阶段失败 → 角色未判定 → 前端兜底走「未判定=居中」，全部气泡居中。
- 落实：① 未判定/失败态气泡恢复左右布局（按代号首现序 A/C/…靠左、B/D/…靠右，与原版 T 左 P 右视觉一致）；② 修复清理失败根因（纯语气词段清理成空串导致校验失败+无效重试）。

### 反馈 2：清理阶段和记录阶段耗时太久

**结论：✅ 采纳——陛下指示不做 provider 测速；慢的根因与现状如实记录，provider 维持 MIMO 不动**

- 实测现象（jobs 日志）：59 段真实音频 clean 单次 ~150s、失败重试两轮共 ~5 分钟；record ~100s。MIMO 长 JSON 输出是主要耗时。
- 处理（不测速）：① provider 维持 MIMO（陛下既定决策），若未来想换，`.env` 一行 `LLM_PROVIDER=qwen/deepseek` 即可，无需测试；② 给 jobs 表加时间戳（当前无，排障靠猜日志）；③ 减少无效重试（失败根因修复后自然省时）。

---

<!-- 新反馈从这里往上追加，格式参照 FB-001 -->
