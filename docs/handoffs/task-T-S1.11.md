# Task T-S1.11: 记录元数据富化 + 分组 + 编辑/删除 API（FB-011，后端）

## 背景

陛下要求：记录带标签/摘要（可编辑、用于分类筛选）；看板可按时间/来源文件名/时长/字数排序筛选；同一音频的记录可分组管理（组名/标签/备注，增删改查）；可删除记录/组（前端确认）；深色主题。本卡只做**后端**（模型+API+prompt），前端另卡（T-S1.12，勿动前端）。

## 一、数据模型（`app/backend/src/psyapp/models.py`）

1. **sessions 表加列**（nullable，走既有 `_heal_missing_columns` 自愈机制，不引 alembic）：
   - `original_filename: Mapped[str | None]`（String(255)）——上传来源文件名；
   - `tags: Mapped[list | None]`（JSON）——分类标签数组；
   - `brief: Mapped[str | None]`（Text）——摘要，≤100 字；
   - `group_id: Mapped[int | None]`（ForeignKey("session_groups.id"), index=True）。
2. **新表 `session_groups`**（类名 `SessionGroup`）：`id` PK、`user_id` FK+index、`name` String(128) 非空、`tags` JSON nullable、`note` Text nullable、`created_at` DateTime 非空。
3. `duration_sec` 已存在（现默认 0），复用；`word_count` 不落库，查询时由 `cleaned_text` 现算。

## 二、上传链路（`routes.py` + `audio.py`）

1. `POST /sessions`：保存 `file.filename` 到 `original_filename`；音频落盘后调新增 `probe_duration_seconds(path) -> int`（放 `audio.py`：`subprocess.run(["ffprobe","-v","quiet","-show_entries","format=duration","-of","csv=p=0",path], timeout=10)`，取浮点秒转 int；任何异常/超时/非数字返回 0，不阻塞上传）写入 `duration_sec`。
2. ffprobe 探测放在建 sessions 行之前即可（同步、快速），失败兜底 0。

## 三、记录生成：record prompt v3 产 brief + tags

1. 新建 `app/backend/prompts/record/v3.md`：**以 v2.md 为底照抄**（客观性硬约束一字不改），仅输出 JSON schema 增加两字段：
   - `"brief"`：一句话客观摘要，**不超过 100 字**，遵守 v2 全部客观性约束（"来访者自述…"句式等）；
   - `"tags"`：1–4 个分类标签数组，优先从常见类目选（咨询/讲授/督导/个体/团体/访谈…），内容不匹配时可自拟，简短（每标签 ≤8 字）。
2. `prompts.py`：`_TEMPLATES["record"]` 版本 v2→v3。
3. `services.py` `parse_record_json`：新增字段**宽松解析**——`brief`（str，缺失给 `""`）、`tags`（list[str]，缺失给 `[]`），不作为必填校验（避免模型偶发缺字段整体失败）。
4. `store_record` 成功后（`_generate_record` 返回非 None 处）：把 `brief`/`tags` 回写到 sessions 行（omni 与 asr 两条路径共用该函数调用点，改一处即可）。

## 四、查询与编辑/删除 API（`routes.py`）

1. **GET /sessions 富化**：每条加 `original_filename / duration_sec / word_count（len(cleaned_text or "")）/ tags（None→[]）/ brief / group_id / group_name（join，无组为 null）`。
2. **GET /sessions/{id}** 详情同样带出 `tags / brief / group_id`。
3. **PATCH /sessions/{session_id}**：body JSON 可选字段 `tags`（str 数组）、`brief`（str，**>100 字抛 422**）、`group_id`（int 或 null，int 时须存在且属当前用户，否则 404）。只更新传入字段，返回更新后摘要字段。
4. **DELETE /sessions/{session_id}**：硬删——segments、records、jobs、sessions 行依次删除 + `audio_path` 文件 `unlink(missing_ok=True)`。返回 `{deleted: session_id}`。
5. **分组 CRUD**（`/groups`）：
   - `GET /groups`：按 created_at 倒序列 `{group_id,name,tags,note,created_at,member_count}`（member_count=组内 sessions 数）；
   - `POST /groups`：body `{name,tags?,note?}`，name 空/重复（同用户内）抛 422；
   - `PATCH /groups/{group_id}`：可改 `name / tags / note`；
   - `DELETE /groups/{group_id}`：删组**不删记录**——组内 sessions 的 `group_id` 置 null。

## 五、测试（`app/backend/tests/` 新增 `test_session_meta.py`）

覆盖：列自愈后新字段读写；GET /sessions 富化字段齐全；PATCH tags/brief/group_id 及 brief>100 → 422、非法 group → 404；DELETE 级联（行+音频文件都没）；分组 CRUD 全链（含重名 422、删组后记录归未分组）。全部离线（临时 SQLite + TestClient，fake LLM，不碰真实 API）。

## 验收标准（自测必须全过并贴证据）

1. `.venv/bin/python -c "import psyapp.main"` 无输出
2. `.venv/bin/python -m pytest app/backend/tests -q` 全过（基线 59，新增数量自报）
3. `.venv/bin/ruff check app/backend` → All checks passed
4. `git diff` 只含后端 + prompts/record/v3.md + 新测试 + 自报，无前端、无越界
5. 自报落 `docs/handoffs/task-T-S1.11-self-report.md` 随分支提交

## 禁止事项

- 不改前端任何文件；不改 clean/omni prompt；不改 `_MODEL_DISPLAY` 展示逻辑之外的既有行为。
- 不引 alembic/新依赖；不加鉴权（dev 单用户，`dev_user_id` 过滤照旧）。
- `tests/audio/` 未跟踪文件勿入提交；不真实调用外部 API（ffprobe 本地命令除外）。
- 不自动合并/推送/打 tag；分支 `task/t-s1.11-record-meta-api`，commit 前缀 `[T-S1.11]`。
