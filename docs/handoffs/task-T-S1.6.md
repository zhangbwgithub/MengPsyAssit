# Task T-S1.6: 双模式管线——Qwen3.5-Omni-Plus 多模态直转 + 上传可选模式

## 背景与契约

陛下拍板（`docs/feedback.md` FB-008 原话）：「把 qwen3.5-omni-plus 直转做成管线的第二种处理模式（双模式并存，上传时可选模式并显式指明模型，未来：模型可选，且 ASR+LLM（paraformer+deepseek）作为实时录音模式的入口）」。

**大统领先导探针（已验证，直接复用，勿重新实验）**：
- 端点：DashScope OpenAI 兼容 `POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`，key = `DASHSCOPE_API_KEY`（.env 已有）。
- 请求体要点：`model: "qwen3.5-omni-plus"`；message content 为数组 `[{"type":"input_audio","input_audio":{"data":"data:;base64,<b64>","format":"mp3"}}, {"type":"text","text":<prompt>}]`；顶层 `"modalities":["text"]`、`"enable_thinking": false`；非流式调用即可。
- 实测：4.1MB/5.5 分钟音频 → 6.4s 完成，输出 17 轮清理稿（格式 `轮次号\t角色\t内容`），质量对标 Kimi。
- 音频 token 约 420/分钟（5.5 分钟=2312 audio tokens）。

分支：`task/t-s1.6-omni-mode`（从 main 开）。提交消息：`[T-S1.6] type: 描述`。
**你不 merge、不 push、不打 tag**；自报写 `docs/handoffs/task-T-S1.6-self-report.md`。

## 输入与环境事实

- 现有管线（asr 模式）一切不动：paraformer → clean v4（deepseek-v4-flash）→ record（deepseek-v4-flash）。
- `providers/openai_compat.py` 的 OpenAICompatLLM 可复用（omni 端点同协议），但 messages 结构是音频多模态数组、且响应取 `choices[0].message.content`——与现有 complete() 的纯文本 messages 不同，需要新方法或新类。
- 探针验证过的转写+清洗 prompt（直接照抄进代码/模板文件，勿改写）：

```
请完整转写这段心理咨询录音，并直接输出清理后的对话稿。要求：
1. 先听完全篇判断两位说话人的角色（咨询师/来访者），在每一轮标注角色。
2. 按对话轮次组织输出：同一人连续说的话合并为一轮；纯语气词（嗯/啊/对）不单独成轮，并入相邻轮次或删除。
3. 清理口语：去除填充词，合并被拆散的句子，修正明显的语音识别错误和指代（根据上下文判断他/她）。
4. 保留原意和说话风格，不添加、不总结。
5. 输出格式（每轮一行）：轮次号	角色	内容
```

## 钉死的决策

### 1. 后端：omni provider + 管线分叉

- `providers/` 新增 `omni.py`：`QwenOmniLLM`，字段：base_url=`https://dashscope.aliyuncs.com/compatible-mode/v1`、model=`qwen3.5-omni-plus`、key env=`DASHSCOPE_API_KEY`；方法 `transcribe_audio(audio_path, prompt) -> str`：读文件→base64→按探针结构组请求（modalities=["text"]、enable_thinking=false）→ 非流式调用 → 返回 content 文本。httpx timeout 给 300s。不放进 get_llm_provider 工厂（它不是文本 LLM，不参与 clean/record）。
- `routes.py`：`POST /sessions` 新增可选表单字段 `mode`（`"omni"` | `"asr"`，**默认 `"omni"`**）；非法值 → validation_error。`mode` 存入 session（新列 `pipeline_mode` String(8)，自愈机制加列）。
- `services.py::run_background_pipeline` 按 mode 分叉：
  - **omni 路径**：transcribe job（type="transcribe"、provider="qwen3.5-omni-plus"）内调 `QwenOmniLLM.transcribe_audio`；解析轮次文本为 segments（见 2）；**无 clean 阶段**（不建 clean job）；record 阶段照旧（deepseek，输入=按 segments 拼的清理稿）。
  - **asr 路径**：现状完全不变。
- GET /sessions/{id} 响应 data 增加 `pipeline_mode` 与 `model_display`（omni → "qwen3.5-omni-plus"；asr → "paraformer-v2 + deepseek-v4-flash"）。

### 2. omni 输出解析（`omni.py` 或 `segments.py`）

- 逐行解析：`^\s*(\d+)\s*[	 ]\s*(咨询师|来访者|[^\t]+?)\s*[	]\s*(.+)$`（角色列取第二字段；容忍「来访者：」带冒号写法——先按 \t 切三字段，切不开则按「序号 角色 内容」首空格容错）。
- 角色映射：「咨询师」→ role=T、「来访者」→ role=P；其他角色文本归 P 兜底并保留原词为 role_label；speaker 代号按角色首现序分配 A/B（同角色多人则 A1/A2 之类沿用现有 SpeakerCode 规则）。
- segment 字段：seq 从 0 重排；content=cleaned_content=该行内容；start_ms/end_ms=**None**（omni 无时间戳）；role/role_label 填上。
- raw_transcript 列存 omni 原始输出。
- 解析出 0 轮 → 视为失败重试 1 次，仍失败 → session failed（同现状语义）。
- 前端时间戳渲染要容忍 None（不显示时间行）。

### 3. 前端

- 上传卡片：模式选择器（两个 radio 卡片，**显式写明模型名**）：
  - ① **多模态直转（推荐）**：模型 `qwen3.5-omni-plus` —— 音频直接听写+清理+角色判定，约 10 秒出稿
  - ② **ASR + LLM 管线**：ASR `paraformer-v2` · 清理 `deepseek-v4-flash` —— 带时间戳，实时录音场景（未来）
  - 默认选中 ①；上传时把 `mode` 带入表单。
- 三阶段进度条按模式自适应：omni 显示两阶段「多模态直转 → 生成记录」；asr 维持三阶段。
- 会话详情：对话稿卡片标题旁/记录卡片元信息区显示当前模式与模型名（`model_display`）。
- 气泡：omni 模式无时间戳行；其余（每人一色、T 左 P 右）复用现状。
- 375px 不破版；不加新依赖。

### 4. 测试

- 现有 46 项全过（asr 路径回归）。
- 新增：mode 默认 omni / 显式 asr / 非法值 400；omni 轮次解析单测（含冒号容错、空行、重试失败路径）——用 monkeypatch 假 provider，不真实调 API。
- GET 返回 pipeline_mode / model_display 断言。

## 禁止清单

- 不改 asr 路径任何行为；不改 clean/record prompt；不动 `.env`；不引新依赖（httpx 已有）。
- 不把音频 base64 写日志；key 掩码沿用现有过滤器。
- 不 merge、不 push、不打 tag。

## 验收标准（大统领逐条实测）

1. pytest 全过 + ruff + 导入自检 + 前端构建。
2. **浏览器实测**（大统领）：选「多模态直转」上传 01 号合成音频 → 进度条两阶段 → 对话稿 17 轮风格输出、模式/模型名显示正确。
3. **陛下真实音频实测**（大统领）：选 omni 模式重跑 56 段音频 → 轮次稿 + 记录三字段齐全、与探针质量一致。
4. asr 模式回归（大统领）：选 asr 模式上传 01 号音频仍正常走三段。
5. 自报在 `docs/handoffs/task-T-S1.6-self-report.md`。

## 门禁

构建 → 测试 → 静态 → 前端构建；提交前 `git diff` 自查只含本卡范围。
