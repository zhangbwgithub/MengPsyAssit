"""应用配置：pydantic-settings 从 .env 读取，文件缺失时用默认值。"""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 各 LLM provider 的默认模型（llm_model 留空时按 provider 填充）
LLM_DEFAULT_MODELS = {
    "mimo": "mimo-v2.5-pro",
    "deepseek": "deepseek-v4-flash",
    "qwen": "qwen-max",
}


class Settings(BaseSettings):
    """全局配置。各 api_key 仅定义，repr 不暴露。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    database_url: str = "sqlite:///data/app.db"
    data_dir: str = "data"
    dev_user_id: int = 1
    dashscope_api_key: str = Field(default="", repr=False)
    xiaomi_cn_api_key: str = Field(default="", repr=False)
    deepseek_api_key: str = Field(default="", repr=False)
    # Provider 选择（D8 架构基石：实现可配置可替换，未知值在工厂处抛错）
    # T-S0.6：LLM 默认切换为 mimo（陛下拍板，成本更低，实测 59/59 标签保真）
    asr_provider: str = "paraformer"
    llm_provider: str = "mimo"
    # llm_model 留空 = 跟随 llm_provider 的默认模型（见下方 validator）；
    # 显式设置（如 LLM_MODEL=qwen-max）则覆盖。这样仅切 LLM_PROVIDER 时模型自动跟随。
    llm_model: str = ""
    # Prompt 模板目录（默认 app/backend/prompts，相对仓库根解析）
    prompts_dir: str = ""

    @model_validator(mode="after")
    def _resolve_llm_model(self) -> "Settings":
        if not self.llm_model:
            self.llm_model = LLM_DEFAULT_MODELS.get(self.llm_provider, "")
        return self

    @model_validator(mode="after")
    def _ensure_data_dir(self) -> "Settings":
        if self.data_dir:
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        return self


_settings: Settings | None = None


def get_settings() -> Settings:
    """懒加载全局 Settings 单例。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
