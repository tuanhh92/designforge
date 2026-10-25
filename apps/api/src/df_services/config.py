"""Settings, read from the environment (see .env.example)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://designforge:designforge@localhost:5432/designforge"
    storage_dir: Path = Path("./var/storage")
    api_public_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"

    ai_provider: Literal["openai", "anthropic", "mock"] = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-5"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"

    geometry_engine: Literal["gltf", "sketchup_mcp"] = "gltf"
    sketchup_mcp_command: str = "python"
    sketchup_mcp_args: str = "extensions/sketchup-mcp-server/server.py"
    # Empty values fall back to ~/.designforge/bridge.json, the same file the SketchUp extension reads.
    df_bridge_config: Path = Path("~/.designforge/bridge.json")
    df_bridge_port: int = 0
    df_bridge_token: str = ""
    df_job_root: Path | None = None

    max_upload_mb: int = 20
    max_images: int = 6
    worker_poll_seconds: float = 0.5
    job_stale_after_seconds: int = 300

    def bridge(self) -> tuple[int, str, Path]:
        """(port, token, job_root) shared with the SketchUp extension; env/.env values win over the file."""
        path = self.df_bridge_config.expanduser()
        file = json.loads(path.read_text()) if path.is_file() else {}
        port = self.df_bridge_port or int(file.get("port", 9877))
        token = self.df_bridge_token or file.get("token", "")
        root = self.df_job_root or Path(file.get("job_root", "~/DesignForge/jobs"))
        return port, token, root.expanduser().resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
