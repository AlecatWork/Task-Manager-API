"""Central application settings.

Every setting is read from environment variables (or the project's .env file), so nothing secret or machine-specific is hard-coded in the source.
"""
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root 
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "Task Manager API"

  
    secret_key: str = Field(default="", validate_default=True)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    # bcrypt work factor: each +1 doubles the time to hash a password.
    
    bcrypt_rounds: int = Field(default=12, ge=4, le=16)

    # --- Database -----------------------------------------------------------
    database_url: str = f"sqlite:///{(BASE_DIR / 'app.db').as_posix()}"

    # --- CORS ---------------------------------------------------------------
    cors_origins: list[str] = [
        "http://localhost:8501",
        "http://127.0.0.1:8501",
        "http://localhost:3000",
    ]

    # --- Background notifications --------------------------------------------
    notification_log_path: str = str(BASE_DIR / "notification_log.txt")
    # Artificial delay that makes the "runs after the response" behaviour easy to see in a demo
    notification_delay_seconds: float = 0

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("secret_key")
    @classmethod
    def secret_key_must_be_strong(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError(
                "SECRET_KEY is missing or shorter than 32 characters. Add it to .env - "
                'generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return value


settings = Settings()
