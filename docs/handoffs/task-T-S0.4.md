# 任务卡 T-S0.4：单页前端（S0 走骨架 · 第 4 张卡）

## 背景与契约

项目「咨询记录助手」：录音 → ASR 转写（T=咨询师/P=来访者）→ 口语清理 → 客观咨询记录生成。S0 走骨架进行中：后端主链路已在 main 分支全通——`POST /sessions` 上传音频 → 后台转写→清理→记录 → `GET /sessions/{id}` 查全量（实测 20 秒级端到端成功）。

本任务：**S0 唯一的前端卡**——Vue3+Vite 最小单页，把主链路可视化：**选文件上传 → 进度/状态 → T/P 着色对话稿 → 清理后文本 → 记录卡片**。做完它，T-S0.5 冒烟演示就能向陛下展示完整产品雏形。

仓库根：/home/houmo/meng/MengPsyAssit。先读 `AGENTS.md` 与 `docs/handoffs/CURRENT.md` 再动手。

## 输入与环境事实（已核实）

- **后端 API（全部已实测可用，端口 8660）**：
  - `POST /sessions`：multipart 表单 `file`（音频）+ 可选 `speaker_zero`（"T"|"P"，默认 T）→ 返回 `{ok, data:{session_id, status:"uploading"}}`
  - `GET /sessions/{id}`：返回 `{ok, data:{session_id, status, segments:[{seq,speaker,content,start_ms,end_ms}], cleaned_text, record:{summary, counselor_work, client_reported_topics, basic_info, status}}}`；status 流转 `uploading→transcribing→done/failed`
  - `GET /sessions`：会话列表
  - 统一错误结构：`{ok:false, error:{code, message}}`
- 后端启动：`DASHSCOPE_API_KEY=*** .venv/bin/python -m uvicorn psyapp.main:app --port 8660`（验收时编排方负责起，你开发自测也可自己起）
- Node v24.15.0 / npm 10.9.7 已装。**npm 网络若慢/失败，用镜像：`npm install --registry=https://registry.npmmirror.com`**
- 前端目录：`app/frontend/`（目前只有 .gitkeep + README）

## 已钉死的路线决策（不给二次选择）

1. **技术栈**：Vue 3（Composition API）+ Vite；**不引 Pinia、不引 vue-router、不引 UI 组件库**——单页直写，原生 CSS（或单文件组件内样式）。禁镀金。
2. **API 代理**：Vite dev server 把 `/api/*` 代理到 `http://127.0.0.1:8660`（去掉 /api 前缀转发）；前端代码一律请求 `/api/sessions...`。同时支持 `VITE_API_BASE` 环境变量覆盖（为 S5 部署留口，一行代码的事）。
3. **页面结构（单页三段式）**：
   - **上传区**：文件选择（限 .wav/.m4a/.mp3/.opus/.flac，前端也做扩展名提示）+ 说话人 0 映射选择（T/P 单选，默认"说话人 0 = 咨询师 T"）+ 上传按钮；提交后显示当前状态轮播（uploading/transcribing...，3s 轮询 `GET /sessions/{id}`）；失败显示后端 error.message + 重试入口（重新上传）
   - **对话稿区**：segments 按 seq 渲染，**T 与 P 双色区分**（如 T 蓝左对齐 / P 绿右对齐，或上下文明确的标签+底色）；段号与时间戳（start_ms 格式化为 mm:ss）低调展示
   - **结果区**：清理后文本（保留 `T:`/`P:` 行格式，等宽或正常排版皆可）+ 记录卡片（概述 / 咨询师的工作 / 来访者话题标签列表）
   - **页脚常驻提示**：「AI 生成内容仅供专业参考」（方案 §6.4 合规要求，必须可见）
4. **状态持久化**：不做（刷新重置即可，S0 故意不做）。
5. **响应式**：桌面 ≥800px 正常布局；手机窄屏（375px）纵向堆叠不破版（媒体查询或弹性布局，实测为准）。
6. **工程文件**：`app/frontend/package.json`（scripts: dev/build/preview）、`vite.config.js`（proxy + base 默认）、`index.html`、`src/`。**node_modules 进 .gitignore**（先读现有规则，缺则补 `node_modules/`）。

## 要求

### 1. 工程初始化与实现（按上述 6 点）

### 2. 构建与自测
- `npm install`（必要时加镜像参数）+ `npm run build` 零错误，产物在 `app/frontend/dist/`
- dev 模式自测：起后端（8660）+ `npm run dev`，用 curl 或你自选的方式确认代理通（`/api/health` 经 Vite 返回 200）
- 写 `tests/e2e/smoke_frontend.sh`：一键起后端+前端（前端用 `npm run preview` 服务 build 产物，端口 5199 之类避开占用；preview 也要配代理或说明替代方案）→ curl 断言：`/` 返回 200 且含关键文案（如"AI 生成内容仅供专业参考"）、`/api/health` 经前端服务可达 → 退出码 0；结果落 `tests/e2e/results/frontend_<时间戳>/` 并 `git add -f`
- ⚠️ 注意：vite preview 默认不带 dev proxy——要么在 `vite.config.js` 给 preview 也配代理，要么 smoke 脚本直接对 8660 验证 /api 链路、前端页面只验静态可达——选一种，注释说明

### 3. 反面清单（违反即验收失败）

- ❌ 不引 Pinia/vue-router/UI 库/状态持久化/多页面
- ❌ 不做录音（S1 的活）、不做编辑/映射/撤销/搜索/登录
- ❌ 不改后端任何代码（发现问题报告，不擅改）；不动 tests/audio/、docs/、prompts/
- ❌ 不把 node_modules/、dist/ 提交进 git
- ❌ 代码/提交中出现 API key 明文
- ❌ 不合并 main、不打 tag

## 验收标准（编排方逐条实测——编排方会用真实浏览器打开页面并真传一段合成音频走完全程）

1. `npm run build` 零错误（编排方复跑）
2. **真浏览器端到端（核心）**：编排方起后端+前端，真实浏览器打开页面 → 选 `tests/audio/01_normal_dialogue.wav` 上传 → 看到状态流转 → 最终渲染 T/P 着色对话稿 + 清理文本 + 记录卡片；全程无 JS 报错
3. 手机视口（375px 宽）页面不破版
4. 「AI 生成内容仅供专业参考」常驻可见
5. 失败路径：上传 .txt → 页面显示后端错误信息而非白屏/静默
6. `smoke_frontend.sh` 退出码 0，结果入库
7. 零密钥泄露（`git grep "sk-"` 新增零命中）
8. git：分支 `task/t-s0.4-frontend`，提交前缀 `[T-S0.4]`（不合并）

## 技术约束

- 前端代码中文界面；注释中文
- 输出全部 UTF-8
- node_modules 不入库；lock 文件（package-lock.json）**入库**
- 交付后在 `docs/handoffs/task-T-S0.4-self-report.md` 留自报——自报不作数，编排方实测为准（本次编排方会用真实浏览器验收）
