# ASR 选型评测结果汇总（T-0.2B）
## 评测条件
- 音频素材：`tests/audio/0{1,2,3}_*.wav`（16kHz 单声道 16bit WAV）
- 黄金基准：`tests/golden/<同名>.json`
- API Key：环境变量 `DASHSCOPE_API_KEY`
- 执行时间：本地实测
- 评测命令：`.venv/bin/python tests/asr_eval/run_eval.py --model all`

## 结果总表
| 候选模型 | 音频 | 状态 | CER | 延迟(s) | 说话人一致率 |
|----------|------|------|-----|---------|--------------|
| paraformer-v2 | 01_normal_dialogue.wav | ok | 0.0227 | 3.28 | 100.00% |
| paraformer-v2 | 02_overlap_interruption.wav | ok | 0.1700 | 3.31 | 100.00% |
| paraformer-v2 | 03_long_pauses.wav | ok | 0.0109 | 3.27 | 100.00% |
| qwen3-asr-flash | 01_normal_dialogue.wav | ok | 0.0114 | 1.36 | N/A |
| qwen3-asr-flash | 02_overlap_interruption.wav | ok | 0.1200 | 0.92 | N/A |
| qwen3-asr-flash | 03_long_pauses.wav | ok | 0.0000 | 0.90 | N/A |
| qwen3-asr-flash-filetrans | 01_normal_dialogue.wav | ok | 0.0170 | 3.28 | N/A |
| qwen3-asr-flash-filetrans | 02_overlap_interruption.wav | ok | 0.1000 | 18.66 | N/A |
| qwen3-asr-flash-filetrans | 03_long_pauses.wav | ok | 0.0000 | 3.29 | N/A |

## 候选横向对比
| 维度 | paraformer-v2 | qwen3-asr-flash | qwen3-asr-flash-filetrans |
|------|---------------|-----------------|---------------------------|
| 平均 CER | 0.0679 | 0.0438 | 0.0390 |
| 平均延迟 | 3.29s | 1.06s | 8.41s |
| 调用方式 | 异步任务 | 同步调用 | 异步任务 |
| 输入要求 | DashScope OSS URL（脚本自动上传） | 本地文件 / URL / base64 | DashScope OSS URL（脚本自动上传） |
| 说话人分离 | ✅ 支持 | ❌ 不支持 | ❌ 不支持 |
| 句级时间戳 | ✅ 支持 | ❌ 不支持 | ✅ 支持 |
| 官方时长规格 | 录音文件识别（分钟级） | 短音频/多模态对话 | 长音频文件转写，支持 180 分钟 |
| 失败组数 | 0 | 0 | 0 |

## 说明
- CER 使用字符级 Levenshtein，归一化去除中英文标点和空白。
- 说话人一致率仅对支持说话人分离的模型计算；其余记为 N/A。
- 延迟包含提交、轮询、结果下载的完整时间（异步任务）或单次请求往返时间（同步任务）。
- 本汇总仅陈列实测数据与官方规格，最终选型由编排方定夺。
