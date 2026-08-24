# MengPsyAssit — 咨询记录助手

> Meng's Psychology Assistant
> 为心理咨询师打造的「录音 → T/P 转写 → 口语清理 → 客观合规咨询记录 → 记录管理」一体化工具。

## 项目状态

**规划阶段** — 方案与任务书已就绪，待确认后进入 P0 技术验证。

## 目录结构

```
MengPsyAssit/
├── README.md                        # 本文件：项目总览与目录导航
├── LICENSE                          # MIT 许可证
├── .gitignore                       # Git 忽略规则（含敏感信息红线）
│
├── docs/                            # 📚 项目文档中心
│   ├── prd/                         #    原始需求文档（PRD）
│   ├── adr/                         #    架构决策记录（滚动追加）
│   ├── progress/                    #    阶段进度周报
│   ├── 00-整体解决方案.md            #    技术架构 / 流程 / 数据模型 / 路线图
│   ├── 01-任务书.md                  #    P0~P4 任务分解与验收标准
│   ├── 02-工作流.md                  #    Hermes × Reasonix 协作规范
│   └── 开发执行契约-v0.2.md          #    方向性决策记录（v0.2 走骨架+垂直增量）
│
├── app/                             # 💻 应用代码
│   ├── backend/                     #    FastAPI 后端（P1 启动）
│   ├── frontend/                    #    Vue3 PWA 前端（P1 启动）
│   └── desktop/                     #    Tauri 桌面采集端（P2 启动）
│
├── tests/                           # 🧪 测试资产
│   ├── audio/                       #    合成测试音频（不碰真实咨询数据）
│   └── golden/                      #    黄金转写基准（人工标注）
│
└── deploy/                          # 🚀 部署配置（docker-compose 等）
```

## 子目录导航

| 目录 | 内容 | 状态 |
|------|------|------|
| [docs/](docs/) | 需求、方案、任务书、工作流、决策记录 | ✅ 已就绪 |
| ├─ [docs/prd/](docs/prd/) | 原始 PRD 文档（docx 原文归档） | ✅ |
| ├─ [docs/adr/](docs/adr/) | 架构决策记录，每个重大决策一文件 | 🕐 滚动追加 |
| └─ [docs/progress/](docs/progress/) | 各阶段进度周报与验收结果 | 🕐 开发后产出 |
| [app/backend/](app/backend/) | FastAPI 后端：认证、音频、转写管线、Provider 抽象层 | 🕐 P1 启动 |
| [app/frontend/](app/frontend/) | Vue3 + Vite PWA：录音、文字稿编辑、记录管理界面 | 🕐 P1 启动 |
| [app/desktop/](app/desktop/) | Tauri 桌面采集端：会议模式双通道采集（豆包式） | 🕐 P2 启动 |
| [tests/](tests/) | 测试音频与黄金基准，隐私安全（纯合成数据） | 🕐 P0 产出 |
| [deploy/](deploy/) | docker-compose、nginx 配置、备份脚本 | 🕐 P1 收尾 |

## 核心文档速读

1. **[整体解决方案](docs/00-整体解决方案.md)** — 云端优先架构、会议模式双通道采集（豆包式）、Provider 抽象层、数据模型、敏捷路线图
2. **[任务书](docs/01-任务书.md)** — P0 技术验证 → P1 MVP → P2 会议模式 → P3 增强，每个任务含前置/输入/产出/验收
3. **[工作流](docs/02-工作流.md)** — 大统领（PM/架构/验收）× Reasonix（编码）分工、三重质量门禁、分支规范

## 技术栈（已钉死决策）

- **云端优先**：ASR/LLM 全流程走云端模型，不依赖本地显卡
- **Provider 抽象层**：Qwen / Deepseek 可配置切换，后期可扩展本地引擎
- **客户端**：PWA（电脑+手机浏览器）+ Tauri 桌面采集端（会议模式，P2）
- **后端**：FastAPI + SQLite(FTS5) + docker-compose 部署

## License

MIT
