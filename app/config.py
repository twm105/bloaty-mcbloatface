from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@db:5432/bloaty"
    anthropic_api_key: str = ""

    haiku_model: str = "claude-3-5-haiku-20241022"
    sonnet_model: str = "claude-3-5-sonnet-20241022"

    class Config:
        env_file = ".env"


settings = Settings()
