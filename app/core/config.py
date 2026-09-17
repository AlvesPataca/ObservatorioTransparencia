from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Observatorio Ceres-Rialma"
    request_timeout_seconds: float = 20.0
    user_agent: str = (
        "ObservatorioCeresRialma/0.1 "
        "(pesquisa academica; dados publicos de transparencia)"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
