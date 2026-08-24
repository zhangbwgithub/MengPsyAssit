# backend/ — FastAPI 后端

**状态**：🕐 P1 阶段启动，当前为预留目录。

## 规划结构

```
backend/
├── routers/      # API 路由（认证/代号/音频/转写/记录）
├── services/     # 业务逻辑层
├── providers/    # AI Provider 抽象层（ASR/LLM，可配置切换）
│   ├── asr/      # Paraformer / Qwen-ASR 实现
│   └── llm/      # Qwen / Deepseek 实现
├── models/       # SQLAlchemy 数据模型
├── prompts/      # LLM 任务 prompt 模板（版本化管理）
│   ├── clean/    # 口语清理
│   ├── record/   # 咨询记录生成
│   └── themes/   # 主题提取（梦/成长/创伤）
└── core/         # 配置、日志、异常、任务队列
```

## 技术选型

- FastAPI + SQLAlchemy + SQLite（FTS5 全文检索）
- 异步任务队列处理转写/清理/记录生成
- JWT 认证 + bcrypt，数据按用户隔离

详见 [../docs/00-整体解决方案.md](../docs/00-整体解决方案.md) 与 [../docs/01-任务书.md](../docs/01-任务书.md)。
