# MengPsyAssit — 咨询记录助手

> Meng's Psychology Assistant
> 为心理咨询师打造的「录音 → T/P 转写 → 口语清理 → 客观合规咨询记录 → 记录管理」一体化工具。

## 项目状态

**规划阶段** — 方案与任务书已就绪，待确认后进入 P0 技术验证。

## 文档导航

| 文档 | 说明 |
|------|------|
| [docs/prd/](docs/prd/) | 原始需求文档（PRD V1.0 草案） |
| [docs/00-整体解决方案.md](docs/00-整体解决方案.md) | 技术架构、流程、数据模型、路线图 |
| [docs/01-任务书.md](docs/01-任务书.md) | P0~P4 任务分解（含依赖拓扑与验收标准） |
| [docs/02-工作流.md](docs/02-工作流.md) | Hermes × Reasonix 协作规范与质量门禁 |
| [docs/开发执行契约-v0.1.md](docs/开发执行契约-v0.1.md) | 方向性决策记录（Prompt Forge 产出） |
| [docs/adr/](docs/adr/) | 架构决策记录（滚动追加） |
| [docs/progress/](docs/progress/) | 阶段进度周报 |

## 目录规划

```
app/
├── backend/    # FastAPI 后端（P1 启动）
├── frontend/   # Vue3 PWA（P1 启动）
└── desktop/    # Tauri 桌面采集端（P2 启动）
tests/          # 合成测试音频 + 黄金转写基准
deploy/         # docker-compose 部署
```

## 技术栈（已钉死决策）

- 云端优先：ASR/LLM 全流程走云端模型（Qwen / Deepseek，可配置 Provider 抽象层）
- 客户端：PWA（电脑+手机浏览器）+ Tauri 桌面采集端（会议模式，P2）
- 后端：FastAPI + SQLite(FTS5)

## License

MIT
