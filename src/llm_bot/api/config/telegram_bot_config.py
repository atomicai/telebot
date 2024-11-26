from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class TelegramBotMode(str, Enum):
    POLLING = "polling"
    WEBHOOK = "webhook"


class TelegramBotConfig(BaseSettings):
    TOKEN: str = ""
    WEBHOOK_URL: str = ""
    MODE: TelegramBotMode

    model_config = SettingsConfigDict(env_prefix='TELEGRAM_BOT_')


telegram_bot_config = TelegramBotConfig()
