# frontend/ — Vue3 PWA 前端

**状态**：🕐 P1 阶段启动，当前为预留目录。

## 规划结构

```
frontend/
├── src/
│   ├── views/        # 页面（登录/录音/文字稿/记录管理）
│   ├── components/   # 组件（录音器/对话稿编辑器/对比视图）
│   ├── stores/       # Pinia 状态管理
│   └── api/          # 后端 API 封装
└── public/           # PWA manifest / 图标
```

## 关键能力

- **录音**：MediaRecorder API，分片上传，断点暂存（IndexedDB）
- **文字稿编辑**：T/P 对话渲染、段落编辑/合并/拆分/切换标签
- **口语清理**：原文对比视图、撤销/重做
- **响应式**：手机 / 平板 / 电脑三端适配
- **PWA**：HTTPS 环境下调用麦克风权限

详见 [../docs/01-任务书.md](../docs/01-任务书.md)（T-1.F1 ~ T-1.F5）。
