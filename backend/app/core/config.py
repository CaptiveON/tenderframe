from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding = "utf-8"
    )

    DATABASE_URL:str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # LLM provider (OpenAI per ARCHITECTURE_NOTES R8)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CLASSIFICATION_MODEL: str = "gpt-5-mini"
    OPENAI_GENERATION_MODEL: str = "gpt-5.1"

    # DEPRECATED — legacy vector store, kept only so old .env files still load
    PINECONE_API_KEY: Optional[str] = None
    PINECONE_INDEX_NAME: Optional[str] = None
    PINECONE_ENVIRONMENT: Optional[str] = None

    # RAG pipeline (BRIEF: dimension and budgets live in settings, never hardcoded)
    EMBEDDING_DIM: int = 1536
    RETRIEVAL_TOP_K: int = 8
    RETRIEVAL_PER_SIDE: int = 30
    # Best-cosine-similarity floor below which retrieval is considered weak and
    # the answer pipeline abstains. Calibrated on the golden set (M3): in-scope
    # questions scored 0.559-0.814, out-of-scope 0.378-0.542.
    ABSTAIN_SCORE_THRESHOLD: float = 0.55
    RERANKER_ENABLED: bool = False
    HYDRATION_MAX_TOKENS: int = 1500
    HYDRATION_MAX_SECTIONS: int = 6
    GOVUK_FETCH_DELAY_MS: int = 500

    # Abuse & cost controls (F1, F2, F11). In-process / single-instance.
    ANSWER_RATE_PER_MIN: int = 12        # per-user answer requests / minute
    ANON_CREATE_PER_HOUR: int = 30       # per-IP anonymous-user creations / hour
    AUTH_RATE_PER_MIN: int = 10          # per-IP login+register attempts / minute
    DAILY_ANSWER_CAP: int = 1000         # global RAG answers / day (spend ceiling)
    MAX_QUESTION_CHARS: int = 4000       # reject oversized questions

    # Transport (F9): comma-separated allowed browser origins.
    CORS_ORIGINS: str = "http://localhost:3000"

settings = Settings()