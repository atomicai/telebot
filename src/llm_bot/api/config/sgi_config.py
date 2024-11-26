from pydantic_settings import BaseSettings, SettingsConfigDict


class SGIConfig(BaseSettings):
    HTTP_PROTOCOL: str = "http"
    HOST: str = "0.0.0.0"
    PORT: int = 7420

    WORKERS_COUNT: int = 1

    AUTO_RELOAD: bool = True
    TIMEOUT: int = 420

    WSGI_APP: str = "llm_bot.api.application:app"
    WORKER_CLASS: str = "uvicorn.workers.UvicornWorker"

    model_config = SettingsConfigDict(env_prefix='SGI_')


sgi_config = SGIConfig()
