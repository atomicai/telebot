from pydantic_settings import BaseSettings, SettingsConfigDict


class SecurityConfig(BaseSettings):
    admin_username: str
    admin_password: str

    model_config = SettingsConfigDict(env_prefix='SECURITY_')

security_config = SecurityConfig()