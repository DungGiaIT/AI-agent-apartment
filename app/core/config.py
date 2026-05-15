from pydantic_settings import BaseSettings
class Settings(BaseSettings):
    # API Keys
    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    # Connections
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    # App Info
    app_name: str = "Agent 1 - Listing Verifier"
    app_version: str = "1.0.0"

    # Server Config
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()