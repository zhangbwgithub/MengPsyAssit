# T-S0.3 自报（不作数，以大统领实测为准）

分支：`task/t-s0.3-main-chain`；提交：`d1d705d [T-S0.3] feat: 最简主链路 API（上传→转写→清理→记录→查询）+ 单测与真实冒烟`

## 做了什么

- 新增 `psyapp` 模块：
  - `audio.py`：扩展名白名单（.wav/.m4a/.mp3/.opus/.flac）+ 流式写入途中 200MB 上限 + uuid4 随机名落盘
  - `segments.py`：speaker 编号→T/P 映射（speaker_zero，默认 T；>1 → U）+ 幂等清空与按 seq 落库 + 拼逐行转写稿
  - `jobs.py`：jobs 三行（transcribe/clean/record）状态与 error 记录
  - `prompts.py`：模板目录可配置（默认 app/backend/prompts，仓库根解析）+ 简单字符串替换占位符
  - `services.py`：后台 pipeline 串行「转写→清理→记录」，坏 JSON 重试 1 次，失败标 failed 记 job.error；会话可重交（复用 POST /sessions）
  - `routes.py`：`POST /sessions`、`GET /sessions/{id}`、`GET /sessions`（统一响应封装）
- `models.Session` 增加 `cleaned_text` 列（S0 最简，记录清理文本供查询）；`Settings` 增加 `prompts_dir`
- `main.py` 挂路由器；`pyproject.toml` 加 `python-multipart`（multipart 上传必需）
- 未改 providers 层与 prompts 模板；未引队列中间件/alembic；未动 tests/audio、tests/golden、docs

## 跑了什么命令 / 结果

| 命令 | 结果 |
|------|------|
| `.venv/bin/python -m pytest app/backend/tests -q` | **23 passed**（原 13 + 新增 10） |
| `.venv/bin/ruff check app/backend tests/e2e/smoke_main_chain.py` | **All checks passed** |
| `.venv/bin/python -c "import psyapp.main"` | import ok |
| `.venv/bin/python tests/e2e/smoke_main_chain.py` | **退出码 0**：状态序列 uploading → transcribing → done；segments=11（含 T/P）；cleaned_text 非空；record 三字段齐全 |
| `curl -F file=@note.txt` 上传 .txt | **HTTP 422** 统一错误 `{ok:false,error:{code:invalid_file_type}}`（非 500） |
| `git grep "sk-[A-Za-z0-9]" tests/e2e/results app/backend/...` | 零命中 |

真实冒烟往返记录强制入库：`tests/e2e/results/20260826_004155/`（health.json / upload.json / final_session.json / smoke.log）；smoke.log 命中 `*.log` 忽略规则，已用 `git add -f` 入库。

## 验收标准对照

1. 单测全绿 23（≥19）：**PASS**
2. ruff 零错误：**PASS**
3. 真实端到端：**PASS**（冒烟退出码 0，done/T+P/cleaned_text/record 三字段，结果落盘）——**以大统领实测为准**
4. 失败路径 .txt：**PASS**（422 统一结构，编排方实测为准）
5. 状态机 uploading→transcribing→done：**PASS**（冒烟日志可见）
6. 随机文件名：**PASS**（uuid4 hex + 扩展名，非原始文件名）
7. 零密钥泄露：**PASS**（git grep 无 sk- 明文；冒烟结果无 key/Authorization）
8. git 分支/前缀/冒烟入库：**PASS**（task/t-s0.3-main-chain，[T-S0.3]，git add -f，未合并）
