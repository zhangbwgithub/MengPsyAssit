# deploy/ — 部署配置

**状态**：🕐 P1 收尾阶段产出，当前为预留目录。

## 规划内容

```
deploy/
├── docker-compose.yml   # nginx + backend 两容器
├── nginx/               # HTTPS 配置、静态资源、反代
└── backup.sh            # SQLite 每日备份 + 音频同步脚本
```

## 部署形态

- **P1**：部署于现有服务器验证（单机起步）
- **后期**：架构可平移阿里云（可用 qianwenai-deploy 技能一键上云）

详见 [../docs/00-整体解决方案.md](../docs/00-整体解决方案.md) §7。
