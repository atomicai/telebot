from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict



class TelegramBotConfig(BaseSettings):
    TOKEN: str = ""
    WEBHOOK_URL: str = ""


    model_config = SettingsConfigDict(env_prefix='TELEGRAM_BOT_')


telegram_bot_config = TelegramBotConfig()
