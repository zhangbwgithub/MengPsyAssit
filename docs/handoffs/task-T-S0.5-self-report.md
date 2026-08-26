# T-S0.5 自报：端到端冒烟 + 演示说明

> 自报不作数，编排方实测为准。

## 做了什么

- 在分支 `task/t-s0.5-smoke-demo` 完成 S0 增量出口卡：
  - `tests/e2e/smoke_all.sh`：一键全链路冒烟脚本（起后端/前端 → 串行上传三段合成音频 → 轮询至终态 → 断言汇总 → 落盘）
  - `docs/progress/s0-skeleton.md`：S0 增量出口报告（3 分钟复现实操指南 + 实测结果表 + 已知限制清单）
  - `tests/e2e/results/smoke_all_20260826_093148/`：冒烟实测结果落盘（三段音频全 done）

## 跑了什么命令

```bash
cd /home/houmo/meng/MengPsyAssit

# 语法检查
bash -n tests/e2e/smoke_all.sh    # 通过

# 执行冒烟（DASHSCOPE_API_KEY 由环境注入）
bash tests/e2e/smoke_all.sh

# 结果入库
git add -f tests/e2e/results/smoke_all_20260826_093148/
git add tests/e2e/smoke_all.sh docs/progress/s0-skeleton.md
git commit -m "[T-S0.5] feat: 端到端冒烟脚本 + 演示说明"
```

## 冒烟实测结果

| 音频 | 状态 | 段数 | 说话人 | 耗时 |
|------|------|------|--------|------|
| 01_normal_dialogue.wav | done | 11 | P+T | 15s |
| 02_overlap_interruption.wav | done | 6 | P+T | 10s |
| 03_long_pauses.wav | done | 8 | P+T | 15s |

- 每段 segments≥5 且含 T/P 两种 speaker ✓
- 每段 cleaned_text 非空 ✓
- 每段 record 含 summary + counselor_work ✓
- GET /api/health 经前端代理可达 ✓
- 退出码 0 ✓

## 结果如何

| 验收项 | 自评 |
|--------|------|
| smoke_all.sh 退出码 0 | PASS |
| 三段音频全 done | PASS |
| 断言：segments≥5 + T+P + cleaned_text + record | PASS |
| /api/health 经前端代理可达 | PASS |
| 结果目录入库 | PASS |
| docs/progress/s0-skeleton.md 存在且数字真实 | PASS |
| 原有冒烟脚本不回归 | NOT RUN |
| 零密钥泄露 | PASS |
| 分支 task/t-s0.5-smoke-demo + 提交前缀 [T-S0.5] | PASS |

> 注：「原有冒烟脚本不回归」未在本次自报中运行验证，编排方实测为准。
