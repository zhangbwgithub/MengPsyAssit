# Task T-S1.1: 角色分离重构——代号转写 + LLM 角色判定 + 气泡着色

## 背景与契约

陛下反馈（见 `docs/feedback.md` FB-001，已合 main）：

1. **转写阶段**：不预定义角色，仅做说话人分离，用代号区分（A/B/C…），去掉前端「说话人映射」选择框。
2. **清理阶段**：LLM 通过对话内容判定具体角色（咨询师 T / 来访者 P；同角色多人用 咨询师A/咨询师B、来访者A 区分）；清理结果前端以**对话气泡**呈现，**每个说话人一种颜色**。
3. 记录生成沿用清理后文本，prompt 风格本期不动（精神动力学风格另行接入，见反馈台账）。

技术偏差说明（已获陛下认可，勿再纠结）：paraformer-v2 不返回性别，代号用性别中性的「说话人 A/说话人 B」，不用 男A/女A。

分支：`task/t-s1.1-role-split`（从 main 开）。提交消息：`[T-S1.1] type: 描述`。
**你不 merge、不 push、不打 tag**；交付后在 `docs/handoffs/task-T-S1.1-self-report.md` 写自报。

## 输入与环境事实（已验证，勿重复踩坑）

- Python `.venv/bin/python`（3.11）；装依赖 `HOME=/home/houmo /home/houmo/.local/bin/uv pip install -p .venv -e "app/backend[dev]"`；命令前缀 `HOME=/home/houmo`。
- 测试：`.venv/bin/python -m pytest app/backend/tests -q`；静态：`.venv/bin/ruff check app/backend`；导入自检：`.venv/bin/python -c "import psyapp.main"`。
- 现有管线（`app/backend/src/psyapp/services.py`）：`run_background_pipeline` 串行 转写→清理→记录，每阶段一行 jobs 表；清理/记录坏 JSON 重试 1 次。
- **说话人映射现状**：`segments.py::apply_speaker_mapping` 把 ASR speaker_id "0"/"1" 映射成 T/P（靠前端传的 `speaker_zero`），>1 → U。本卡要**整个移除**这条映射链。
- **paraformer 输出**：`providers/paraformer.py::parse_transcript`，`Segment.speaker` 是 speaker_id 字符串（"0"/"1"/…），无性别信息。
- **Segment 表**（`models.py`）：`speaker` 为 String(1)。SQLite 不校验 varchar 长度，但为整洁把定义放宽到 String(8)（SQLite 无需 ALTER）。新增列靠 `db.py::_heal_missing_columns` 自愈（dev 库自动补列，已验证机制）。
- **Prompt 机制**：`prompts.py::_TEMPLATES` 注册名→(目录, 版本, 占位符)；模板在 `app/backend/prompts/<name>/v1.md`。红线是「勿动现有 v1 文件」——你**新增** `clean/v2.md`、`record/v2.md` 并把注册表指向 v2。
- **前端**：`app/frontend/src/App.vue` 单文件组件（无路由无 Pinia）；有 `speaker_zero` 单选（`.speaker-row`）、T/P 双色气泡、记录卡片。构建 `cd app/frontend && npm run build`。
- **e2e**：`tests/e2e/smoke_all.sh` 上传时带 `-F speaker_zero=T`，需同步去掉。
- 现有单测 `app/backend/tests/test_sessions.py` 用 FakeASR/FakeCleanLLM/FakeRecordLLM（monkeypatch `psyapp.routes.get_asr_provider` / `get_llm_provider`），改契约后这些 fake 与断言必须同步更新。

## 钉死的决策（不得二次讨论）

1. **代号规则**：按说话人首次出现顺序分配 A、B、C…（ASR speaker_id 去重后按首现序），`segments.speaker` 存 "A"/"B"/…；不再存 T/P。
2. **API 契约**：
   - `POST /sessions`：删除 `speaker_zero` Form 参数及其 422 校验（多余字段忽略不报错）；响应不变。
   - `GET /sessions/{id}`：每个 segment 增加 `role`（"T"/"P"/null，清理判定后才有）、`role_label`（如 "咨询师A"/"来访者"/null）、`cleaned_content`（清理后文本，未清理为 null）。原 `speaker` 字段继续返回（代号）。
3. **清理阶段输出契约（clean prompt v2）**：LLM 输出单个 JSON 对象（可剥 ```json 围栏）：
   ```json
   {
     "roles": {"A": {"role": "T", "label": "咨询师"}, "B": {"role": "P", "label": "来访者"}},
     "cleaned": [{"seq": 0, "text": "清理后文本"}, ...]
   }
   ```
   - `roles` 键=输入中出现过的全部代号；role ∈ {T, P}；同角色多人 label 加序号（"咨询师A"/"来访者B"），两人标准场景 label 就是 "咨询师"/"来访者"。
   - `cleaned` 与输入逐段一一对应（seq 对齐），清理规则沿用 v1（删口头禅、保原意、不新增信息），只是把 T/P 标签换成代号。
   - 解析失败/字段缺失/代号不覆盖/seq 不齐 → 重试 1 次，仍失败标 failed（与现有重试结构一致）。
   - 判定后写回：segments.role/role_label/cleaned_content；`sessions.cleaned_text` 仍生成（`角色标签: 清理文本` 逐行拼接，供 record 阶段与调试）。
4. **record prompt v2**：输入改为带角色标签的清理后文本（"咨询师: …"/"来访者: …"），输出 schema 与解析不变（summary/counselor_work/client_reported_topics 三字段），叙述风格不动。`prompt_version` 升为 "v2"（basic_info 与前端元信息自动跟随）。
5. **前端**：
   - 删除说话人映射单选区与相关状态/提交字段。
   - 气泡列表单一来源：segments；文本优先 `cleaned_content`，无则 `content`。
   - 标签：有 `role_label` 显示之，否则显示 "说话人 A" 式。
   - **每人一色**：按代号首现序分配调色板（≥6 个区分度高的颜色，如 蓝/绿/琥珀/紫/玫红/青，背景浅色+边框同色系，文字深色可读）。对齐：role=T 靠左，role=P 靠右，未判定居中或统一靠左——选一并在自报说明。
   - 状态提示「正在转写与生成记录…」保留；记录卡片渲染不动（仅元信息版本号随 basic_info 变化）。
   - 375px 不破版。
6. **多说话人**：>2 个代号时角色判定照常工作（同角色多人 ABC 区分），单测覆盖 3 代号场景。
7. 红线不变：`.env` 由编排方管，不新建；key 不进代码/日志/自报；`tests/audio/`、`tests/golden/`、`app/backend/prompts/v1*`（现有 v1.md 文件）勿动。

## 需求（正面清单）

1. 后端：移除 speaker_zero 全链路（routes/services/enums 中相关用法）；segments 落库改为代号制。
2. 后端：clean 阶段升级为「清理+角色判定」，新增 JSON 解析函数（参照 `parse_record_json` 的严格风格）；写回 role/role_label/cleaned_content；重建 cleaned_text。
3. 后端：`models.py` Segment 新增 role/role_label/cleaned_content 列（全 nullable）+ speaker 放宽 String(8)；`_heal_missing_columns` 机制自动兼容旧库（验证它对新列生效，若该机制按模型反射对账则无需改）。
4. Prompt：新增 `clean/v2.md`、`record/v2.md`（自含示例，代号输入→JSON 输出）；`prompts.py` 注册表切到 v2。
5. 前端：按钉死决策 5 重构气泡与上传区。
6. 测试：更新 `test_sessions.py` 全部受影响用例；新增：3 代号角色判定、clean 坏 JSON 重试后 failed、GET 返回 role/cleaned_content 字段。全部无网络（fake provider）。
7. e2e：`smoke_all.sh` 去掉 speaker_zero；脚本断言更新（段数/说话人断言改为「代号≥2 种且 role 含 T 和 P」）。

## 禁止清单（违反即验收失败）

- 不引 alembic/Celery/Redis/新依赖（前端不得加新 npm 包）。
- 不改 paraformer provider 的调用方式（OSS 上传/轮询逻辑勿动）。
- 不动 `tests/audio/`、`tests/golden/`、`app/backend/prompts/clean/v1.md`、`record/v1.md`。
- 不做记录风格（精神动力学）改造、不做性别识别、不做段级编辑功能。
- 不 merge、不 push、不打 tag、不碰 `.env`。
- 不镀金：不在本卡范围外重构。

## 验收标准（大统领逐条实测，自报不作数）

1. `.venv/bin/python -m pytest app/backend/tests -q` 全过；`ruff check app/backend` 干净；导入自检过。
2. `POST /sessions` 不带 speaker_zero 正常受理；带了也不报错（忽略）。
3. 真实端到端（大统领跑，你不用管）：上传 01 号合成音频 → done；segments 代号 A/B，role 判定 T+P 各至少 1，cleaned_content 非空，记录三字段齐全。
4. 单测覆盖 3 代号场景且过。
5. 前端构建成功；浏览器实测：无映射单选、气泡每人一色、标签显示判定角色、375px 不破版（大统领用 headless Chrome 复验）。
6. `git grep -n "speaker_zero"` 无残留（含前端与 e2e 脚本）。
7. 自报在 `docs/handoffs/task-T-S1.1-self-report.md`（做了什么/跑了什么命令/结果如何，逐条对照验收标准报 PASS/FAIL/NOT RUN）。

## 技术约束与门禁

- 提交前自查 `git diff`：只含本卡范围，无残留文件、无二进制、无 key。
- 门禁顺序：构建（uv install + import 自检）→ 测试（pytest）→ 静态（ruff）→ 前端构建。
- 完成定义 = 上述验收 1/2/4/6/7 你自测通过 + 大统领实测 3/5 通过。
