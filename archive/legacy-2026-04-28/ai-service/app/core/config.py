from pydantic_settings import BaseSettings
from typing import Literal
import os


class Settings(BaseSettings):
    # Server
    ai_service_host: str = "0.0.0.0"
    ai_service_port: int = 8000
    debug: bool = True
    log_level: str = "INFO"

    # LLM
    llm_provider: Literal["openai", "anthropic", "local"] = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-haiku-20240307"

    # Embeddings
    embedding_provider: Literal["openai", "local"] = "local"
    local_embedding_model: str = "all-MiniLM-L6-v2"

    # FAISS
    faiss_index_path: str = "./data/faiss_index"

    # Database
    sqlite_db_path: str = "../backend/data/closetiq.db"

    # RAG
    rag_top_k: int = 5
    rag_score_threshold: float = 0.3
    rag_max_tokens: int = 2000

    # CORS
    allowed_origins: str = "http://localhost:3000,http://localhost:3002,http://localhost:5173"

    class Config:
        # Load local .env first, then root .env — root overrides shared vars
        env_file = (".env", "../.env")
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]


settings = Settings()
