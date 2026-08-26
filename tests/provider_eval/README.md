# provider_eval

真实冒烟：`DASHSCOPE_API_KEY=*** .venv/bin/python tests/provider_eval/smoke_providers.py [--asr|--llm]`，结果（含 API 往返原文）落盘 `results/<时间戳>/`。

LLM 三模型冒烟（T-S0.6）：`.venv/bin/python tests/provider_eval/smoke_llm_providers.py [--basic|--chain]`——mimo/deepseek/qwen 各一次最小 completion + 默认 mimo 完整 clean+record 链路（golden 01 对话稿），结果同样落盘 `results/<时间戳>/`，出库前全量扫描零 key 泄露。三 key 由 `.env` 提供（XIAOMI_CN_API_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY）。
