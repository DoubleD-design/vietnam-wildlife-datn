from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "wildlife_library"
    mongodb_species_collection: str = "species"
    mongodb_species_raw_collection: str = "species_raw"
    app_name: str = "wildlife-ai"
    rag_project_dir: str = "app/rag_runtime"
    cerebras_api_key: str = ""
    cerebras_model: str = "qwen-3-235b-a22b-instruct-2507"
    cerebras_api_url: str = "https://api.cerebras.ai/v1/chat/completions"
    rag_top_k: int = 4
    rag_max_api_retries: int = 3
    rag_max_retry_wait_seconds: int = 3

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
