import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    LOCAL_LLM_URL: str = "http://localhost:11434/v1"
    LOCAL_LLM_MODEL: str = "qwen2.5-coder"
    EMBEDDINGS_MODEL: str = "all-MiniLM-L6-v2"
    SANDBOX_DIR: str = r"E:\EMMA_INDIA_RUN\EMMA_hack2skill\sandbox_jail"
    MANIFOLD_DB_PATH: str = r"E:\EMMA_INDIA_RUN\EMMA_hack2skill\manifold.db"
    PORT: int = 8000

    # Read from .env file inside backend directory
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
