from pydantic_settings import BaseSettings


class KVSettings(BaseSettings):
    ai_model_base_url_key: str = "model_base_url"
    ai_model_openai_api_key_key: str = "model_openai_api_key"
    ai_model_promt_key: str = "model_promt"
    ai_model_temperature_key: str = "model_temperature"
    ai_model_max_tokens_key: str = "model_max_tokens"
    ai_model_openai_default_model_key: str = "model_openai_default_model"
    ai_model_edit_interval_key: str = "model_edit_interval"
    ai_model_initial_token_threshold_key: str = "model_initial_token_threshold"
    ai_model_typing_interval_key: str = "model_typing_interval"


kv_settings = KVSettings()
