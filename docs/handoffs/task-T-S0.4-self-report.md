# T-S0.4 自报：单页前端（Vue3 + Vite）

> 自报不作数，编排方实测为准。

## 做了什么

- 在分支 `task/t-s0.4-frontend` 完成 S0 单页前端：
  - `app/frontend/package.json`：Vue 3 + Vite，scripts dev/build/preview。
  - `app/frontend/vite.config.js`：dev 与 preview 均配置 `/api` 代理到 `127.0.0.1:8660`，并支持 `VITE_API_BASE` 覆盖。
  - `app/frontend/index.html`：静态页面兜底，含合规提示文案。
  - `src/main.js` + `src/App.vue`：单页三段式 UI（上传区/对话稿区/结果区）+ 3s 轮询 + T/P 双色对话泡 + 失败显示后端错误 + 响应式布局 + 页脚常驻「AI 生成内容仅供专业参考」。
- 编写 `tests/e2e/smoke_frontend.sh`：一键起后端 + 前端 preview，curl 断言页面与 `/api/health` 代理可达。

## 跑了什么命令

```bash
cd /home/houmo/meng/MengPsyAssit/app/frontend
npm install
npm run build          # 零错误，产物 dist/
npm run preview -- --port 5199  # preview 代理 /api 到 8660

cd /home/houmo/meng/MengPsyAssit
tests/e2e/smoke_frontend.sh      # PASS，结果入 tests/e2e/results/frontend_20260826_090557/

.venv/bin/python -m pytest app/backend/tests -q  # 24 passed
.venv/bin/ruff check app/backend                  # All checks passed!
```

## 结果如何

| 验收项 | 自评 |
|--------|------|
| `npm run build` 零错误 | PASS |
| 单页三段式 UI 实现 | PASS |
| `/api` 代理 dev + preview 双通 | PASS |
| smoke_frontend.sh 退出码 0 | PASS |
| 后端 pytest 全绿 | PASS |
| 新增代码无 `sk-` 明文 | PASS |

已 `git add` 前端工程文件、lock 文件、`smoke_frontend.sh` 与冒烟结果目录（失败中间结果已清理）。未合并 main、未打 tag。
