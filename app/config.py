from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@db:5432/bloaty"
    anthropic_api_key: str = ""

    haiku_model: str = "claude-sonnet-4-5-20250929"  # Using Sonnet 4.5 for faster meal analysis
    sonnet_model: str = "claude-sonnet-4-5-20250929"

    class Config:
        env_file = ".env"


settings = Settings()
