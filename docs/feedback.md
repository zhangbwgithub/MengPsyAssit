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

## FB-003 · 2026-08-27 · 转写显示简化 + 语义重拼/纠错 + 清洗 skill sourcing + 进度条

> 陛下已确认理解：转写阶段气泡居中是角色未判定的中间态，清理完成后回归左右对话布局。

### 反馈 1：转写阶段的文字和角色可以简化显示

**结论：✅ 采纳，纳入任务卡（T-S1.3 规划）**

- 落实：转写完成但清理未完成时，气泡展示简化（去掉冗余元信息，紧凑样式），明确这是「原始转写」中间态。

### 反馈 2：断句不准（最大问题）——清理阶段按语义重新拼接划分角色 + 语义纠错（如 他→她）

**结论：✅ 采纳，纳入任务卡（T-S1.3 规划，本条为核心）**

- 实测问题：01:03/01:07 同一人一句话被拆成上下两半；02:45/02:49/02:51 同一人连续三段口语碎片——paraformer 按语音停顿断句，不懂语义。
- 落实方向：清理阶段升级为「语义重拼」——LLM 按语义合并同一说话人的碎片段、重划段落边界，同时纠正指代（如上下文是来访者谈妻子，后文「他」纠为「她」）与明显错别字。需要新的输出结构（合并后段落与原始段不再 1:1）。

### 反馈 3：sourcing 对话转写清洗 skill（断句/语法/别字），非常重要

**结论：✅ 调研完成，找到高匹配方法论——采用「蒸馏嵌入」而非整体引入（详见下）**

- 重点考察：断句修正 / 语法纠正 / 别字修正 三类能力。
- 调研范围（2026-08-27，大统领实测）：GitHub 仓库搜索 14 组关键词（asr correction/transcript cleanup/speech-to-text post-processing/diarization merge 等）+ awesome-agent-skills 目录 + 各候选仓库源码精读。
- **最优匹配：`zxkane/audio-transcriber` v1.7.1**（★8，FunASR/Paraformer 家族 + LLM 后处理的成熟 agent skill），其方法论与陛下诉求逐条对上：
  | 其方法 | 对应陛下诉求 |
  |---|---|
  | Phase 2 规则合并：同一说话人连续段（间隔<2s）先合并再交给 LLM | 断句碎片（02:45/02:49/02:51）预合并 |
  | Phase 3 LLM 清理规则「合并口吃/重复表达为流畅句子」 | 语义重拼 |
  | 「基于上下文修正明显 ASR 错误（同音字）」 | 他→她 这类指代/别字纠正 |
  | 「修正语法错误，保持可读性」「保留原意不新增内容」 | 语法纠正且不镀金 |
  | 长音频按 15 分钟分块调用（`chunk_by_duration(900000ms)`） | 顺带缓解长转写的清理耗时 |
- 次相关候选（均不采用，记录备查）：`danielrosehill/Voice-Cleanup-Prompt-Experiment`（10 档清理力度对照实验，结论：Moderate 档=去填充词+STT 纠错是转写清理甜点，重度改写会失真）、`elbruno/ElBruno.S1Mini`（本地填充词清理）、`yunye123/interview-soul-editor`（访谈逐字稿剪辑向）。
- **处理决策：不整体引入该 skill**（它是完整本地转写管线，与我们的云端 paraformer 主链路重叠且依赖重），而是把其 Phase 2+3 方法论**蒸馏进 clean prompt v3** + 后端规则预合并 + 分块机制——在 T-S1.3 任务卡中落实。调研来源：https://github.com/zxkane/audio-transcriber

### 反馈 4：上方增加进度条，让用户清楚目前在哪个阶段

**结论：✅ 采纳，纳入任务卡（T-S1.3 规划）**

- 落实：上传区上方三阶段进度条（转写 → 清理+角色判定 → 记录生成），随会话状态推进高亮；失败态显示失败所在阶段。

---

## FB-004 · 2026-08-27 · 「处理失败」排查——长转写 seq 数错

### 反馈：为什么会显示「处理失败」？

**结论：✅ 根因查明，修复卡 T-S1.4 已派单**

- 现场：陛下上传 56 段真实音频（会话25），清理阶段失败，错误 `source_seqs 未覆盖全部输入段落（期望[0..55]，实际[0..56]）`。
- 根因：T-S1.3 的 clean v3 输入只给 `代号: 文本` 逐行稿，让 LLM 自己数行号当 seq——56 段长文本下模型多数出一个虚构序号，两次尝试均被严格校验拒绝。
- 修复：输入每行显式带 `[seq]` 编号（含分块路径的全局口径），prompt 明确「逐字引用编号、不得数行号」；严格校验保留作安全网。
- 验收：修复后重跑会话25 同音频必须 done。

---

## FB-005 · 2026-08-28 · cermethod.md 推荐组合调研 + Hermes skill + DeepSeek-v4-flash 清洗模型

### 反馈：调研 cermethod.md 推荐组合是否是好方案；是则做成 Hermes skill；同时启用 DeepSeek-v4-flash 作为清洗模型

**结论：✅ 部分采纳——框架整体不适合直连（离线评测 harness），但其核心方法论极有价值，已蒸馏封装成 skill；清洗模型切换已派单（T-S1.5）**

**调研实证（2026-08-28，大统领）：**

1. **teamtee/LLM-ASR-Error-Correction（★19，华科 Dain 团队）**：精读源码+配置+PromptList 后判定——它是**离线批量评测框架**：需要 gold label（text 文件 + 标签文件）、计算 CER 改进，1758 文件中绝大多数是 AISHELL/Librispeech 实验结果。**无法直接接入我们的在线管线**（我们无 gold label、是 live pipeline）。但其方法论是金子：
   - **拼音推理链纠错**：定位错字 → 转有声调拼音 → 生成同音候选 → 按上下文选择——专治 ASR 同音字错误（本项目「他/她」类错误的根源）
   - **保守阈值机制**：读音差别过大/没把握时**保留原文**，用 `<改>/<原>` 标记——防过度改写，与 CoC 阈值思想同源
   - **实测参数**：temp=0.2 / top_p=0.4、每请求 30 句批量
   - 实测效果：AISHELL-1 DeepSeek CER -13%（5.17→4.48）
2. **CoC 阈值思想**：已体现在上述「保守纠错」原则中；两遍清洗管线（TranscriptEnhancer）与本项目单次语义重拼相比性价比低（多一次全量 LLM 调用=耗时翻倍），不采纳。
3. **ct-punc 标点恢复**：不适用——本项目用云端 paraformer-v2 录音文件识别（自带标点），ct-punc 是本地 FunASR 模型。
4. **pycorrector**：独立中文纠错库，需额外依赖与模型下载，其能力已被 LLM 清洗覆盖，不采纳。
5. **关键新发现——deepseek-v4-flash 是推理模型**（大统领实测探针）：
   - 默认带 thinking：简单纠错请求输出 245 tokens 中 240 个是推理 tokens，3.0s
   - `thinking: {type: disabled}`：**0.7s**（4.3x 提速），输出质量不变
   - DeepSeek API 硬性要求：关闭思考时 temperature 必须 = 0.2
   - `.env` 已有 DEEPSEEK_API_KEY，provider 工厂早已接好（默认模型正是 deepseek-v4-flash）

**处理：**
- ✅ 封装为 Hermes skill `asr-transcript-cleanup`（teamtee 拼音推理链 + CoC 保守阈值 + zxkane 管线方法论 + 模型接入清单），可复用于任何 ASR 后处理项目
- ✅ 工作流改进派单 T-S1.5：清洗阶段独立切换到 deepseek-v4-flash（关 thinking、temp=0.2），record 阶段维持 MIMO 不动（陛下 T-S0.6 既定决策）；clean prompt 升 v4 吸收拼音推理链方法论
- ⏳ 验收标准：陛下真实音频实测耗时对比（基线：59 段 124.8s / 56 段 293.8s，MIMO v3）

---

<!-- 新反馈从这里往上追加，格式参照 FB-001 -->
