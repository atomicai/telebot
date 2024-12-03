from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseSettings):
    base_url: str
    openai_api_key: str
    promt: str
    temperature: float
    max_tokens: int
    openai_default_model: str
    edit_interval: int
    initial_token_threshold: int
    typing_interval: int

    model_config = SettingsConfigDict(env_prefix='MODEL_')


model_settings = ModelSettings()
