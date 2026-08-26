# task-T-S0.6-R1 自报

修复 `app/backend/src/psyapp/providers/paraformer.py` 的 `_upload_oss`：向 `subprocess.run` 传入 `env={**os.environ, "DASHSCOPE_API_KEY": self._api_key}`，确保干净启动时 dashscope CLI 能读取到 API key；未使用命令行 `-k/--api-key` 避免进程列表泄露。

新增单测 `test_upload_oss_passes_api_key_via_env`（`tests/test_providers.py`），mock 子进程调用并断言 env 含正确假 key。

门禁结果：
- `pytest app/backend/tests -q`：29 passed（原 28 + 新增 1）
- `ruff check app/backend`：All checks passed
- 代码/测试中无真实 API key 明文
