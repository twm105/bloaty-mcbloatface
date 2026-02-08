from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@db:5432/bloaty"
    anthropic_api_key: str = ""
    redis_url: str = "redis://redis:6379/0"

    haiku_model: str = "claude-sonnet-4-5-20250929"  # Using Sonnet 4.5 for faster meal analysis
    sonnet_model: str = "claude-sonnet-4-5-20250929"

    # Anthropic API timeout settings (seconds)
    anthropic_timeout: int = 180  # 3 minutes for web search operations
    anthropic_connect_timeout: int = 10  # Connection establishment

    # AI cost tracking (per 1K tokens in cents)
    sonnet_input_cost_per_1k: float = 0.3  # $0.003 per 1K input tokens
    sonnet_output_cost_per_1k: float = 1.5  # $0.015 per 1K output tokens

    # Diagnosis thresholds
    diagnosis_min_meals: int = 3
    diagnosis_min_symptom_occurrences: int = 3

    # Auth settings
    session_secret_key: str = ""  # Required in production
    session_cookie_name: str = "bloaty_session"
    session_max_age: int = 86400 * 7  # 7 days
    session_cookie_secure: bool = False  # True in production

    class Config:
        env_file = ".env"


settings = Settings()
