# Task T-S1.8: 称呼语翻转校正——omni 角色判定确定性兜底

## 背景与契约

陛下实测（2026-08-28）：T-S1.7 的 prompt v2 上线后，前端上传 05 号对抗音频（会话44）**开头角色仍翻转**（第2轮「雨生老师，你怎么从来都不休假」被标成咨询师）。大统领追加探针实证：`temperature=0.0` + v2 prompt 连跑 2 次，run1 开头对 / run2 开头仍翻——**prompt 软约束 + 降随机均无法根治，必须加确定性代码兜底**。

**称呼语铁证逻辑**（陛下黄金稿背书）：若一轮内容以「某老师，」开头称呼对方，说话人一定不是该老师本人。当模型把这轮标成「咨询师」时，全篇角色必已翻转——代码可直接对调全部轮次角色，无需再猜。

分支：`task/t-s1.8-omni-flip-guard`（从 main 开）。提交消息：`[T-S1.8] type: 描述`。
**你不 merge、不 push、不打 tag**；自报写 `docs/handoffs/task-T-S1.8-self-report.md`。

## 钉死的改动（只动 `app/backend/src/psyapp/providers/omni.py` + 测试）

### 1. 请求体加温度锁定
`QwenOmniLLM.transcribe_audio()` 的请求体 body 中，与 `"modalities": ["text"]`、`"enable_thinking": False` 同级，加一行：`"temperature": 0.0`。
（大统领已实测 DashScope qwen3.5-omni-plus 接受该参数，两次调用无报错。）

### 2. 新增称呼语翻转校正函数（确定性规则）

```python
_ADDRESS_FLIP_RE = re.compile(r"^[\u4e00-\u9fa5A-Za-z]{1,6}老师[，,？！!?。.]")
```

新函数 `fix_role_flip_by_address(turns: list[tuple[str, str]]) -> list[tuple[str, str]]`（签名可微调，语义不变）：
- 输入/输出均为 `(role_label, content)` 列表（解析后、角色映射前的中间形态，由你按现有 `parse_omni_transcript` 内部结构选最顺的接入点）。
- 扫描规则：**任意一轮**的 role_label 为「咨询师」且 content 匹配 `_ADDRESS_FLIP_RE`（即内容以「X老师」+标点开头，称呼对方为老师）→ 判定全篇翻转。
- 翻转动作：把**所有轮次**的 role_label 中「咨询师」↔「来访者」互换（其他角色标签不动）。
- 只翻转一次（检测到即翻，不重复判断）。
- 未命中规则时原样返回，零副作用。

接入点：`parse_omni_transcript()` 在逐行解析出轮次列表后、做角色映射（咨询师→T/来访者→P）之前，调用该函数。确保翻转后的 segments 的 role/role_label/speaker 代号分配全部基于校正后的角色。

### 3. 测试（`tests/test_omni_mode.py` 追加，全部离线不真实调 API）

- ① 翻转触发：构造 omni 原始输出字符串，其中「咨询师」轮以「雨生老师，你怎么从来都不休假」开头 → 解析后该轮 role=P/来访者、原「来访者」轮全变 T/咨询师。
- ② 不触发（常规对话）：「来访者」轮以「王老师，我最近睡不好」开头（来访者称呼咨询师为老师是正常语态）→ 解析结果零变化。
- ③ 不触发（正文提及非称呼）：「咨询师」轮内容为「你刚才提到老师说的那句话」（「老师」不在句首称呼位）→ 零变化。
- ④ 请求体断言：现有 QwenOmniLLM 请求结构测试中补 `temperature == 0.0` 断言。
- 现有 54 项全过（回归）。

## 禁止清单

- 不改 prompt 常量（v2 已陛下拍板，勿动一字）；不改 asr 路径；不动 `.env`；不引新依赖。
- 不做配置开关、不做翻转日志落库之类镀金——本卡只加一个确定性校正 + 温度参数。
- 不 merge、不 push、不打 tag。

## 验收标准（大统领逐条实测）

1. pytest 全过 + ruff + 导入自检 + 前端构建。
2. **05号对抗音频实测**（大统领）：线上 omni 模式上传 05 号，开头轮（「雨生老师…」句）角色=来访者；逐轮对齐黄金稿正确率 ≥77% 且开头零翻转。
3. **01号常规音频回归**（大统领）：正常出稿、角色不错、校正规则不误触发。
4. 自报在 `docs/handoffs/task-T-S1.8-self-report.md`。

## 门禁

构建 → 测试 → 静态；提交前 `git diff` 自查只含本卡范围。
