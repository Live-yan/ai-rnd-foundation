from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FACTORY_", env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://factory:change-me@localhost:5432/factory"
    data_dir: Path = ROOT / "data"
    upstream_dir: Path = ROOT / ".vendor" / "FastapiAdmin"
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    task_queue: str = "ai-rnd-v1"
    token: str = ""
    model_base_url: str = "http://localhost:4000/v1"
    model_api_key: str = ""
    model_name: str = "factory-planner"
    model_timeout: int = 90
    model_max_tokens: int = 6000
    serena_url: str = ""
    serena_token: str = ""
    cube_api_url: str = ""
    cube_api_key: str = ""
    cube_template: str = ""
    coder_url: str = ""
    coder_token: str = ""
    coder_template_id: str = ""
    coder_owner_id: str = ""
    public_url: str = "http://localhost:8000"
    verifier_image: str = "ai-rnd-verifier:0.1.0"
    docker_host_data_dir: str = ""
    openspec_required: bool = True
    diagrams_required: bool = True

    def ensure_paths(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    return Settings()
