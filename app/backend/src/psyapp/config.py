"""应用配置：pydantic-settings 从 .env 读取，文件缺失时用默认值。"""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。dashscope_api_key 仅定义，repr 不暴露。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "dev"
    database_url: str = "sqlite:///data/app.db"
    data_dir: str = "data"
    dev_user_id: int = 1
    dashscope_api_key: str = Field(default="", repr=False)
    # Provider 选择（D8 架构基石：实现可配置可替换，未知值在工厂处抛错）
    asr_provider: str = "paraformer"
    llm_provider: str = "qwen"
    llm_model: str = "qwen-max"
    # Prompt 模板目录（默认 app/backend/prompts，相对仓库根解析）
    prompts_dir: str = ""

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
