from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bitrix_webhook_url: AnyHttpUrl
    bitrix_timeout_seconds: float = Field(default=30, gt=0, le=120)
    bitrix_rate_limit_per_second: float = Field(default=2, gt=0, le=10)
    bitrix_max_retries: int = Field(default=3, ge=0, le=8)
    bitrix_mask_personal_data: bool = True
    bitrix_rules_config: Path = Path("config/audit-rules.example.json")

    @property
    def webhook_secret(self) -> SecretStr:
        return SecretStr(str(self.bitrix_webhook_url))
