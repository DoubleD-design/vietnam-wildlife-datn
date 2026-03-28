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
    vision_use_remote_backbone: bool = False
    vision_backbone: str = "hf-hub:imageomics/bioclip"
    vision_local_arch: str = "ViT-B-16"
    vision_model_weights_path: str = "../Training/bioclip_model/best_model.pth"
    vision_class_mapping_path: str = "../Training/bioclip_model/class_mapping.json"
    vision_top_k: int = 6
    vision_min_confidence: float = 0.0
    vision_download_timeout_seconds: int = 20
    hf_home: str = ""
    hf_hub_offline: str = ""
    hf_token: str = ""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
