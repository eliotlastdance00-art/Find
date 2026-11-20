"""Application settings, read from environment variables prefixed with ``DFD_`` (or .env)."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DFD_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    weights_dir: Path = Path("weights")
    database_url: str = ""
    secret_key: str = ""
    token_ttl_hours: int = Field(default=12, ge=1, le=24 * 30)
    allow_registration: bool = True
    frame_ancestors: str = "'self'"
    admin_username: str = ""
    admin_password: str = ""

    max_upload_mb: int = Field(default=200, ge=1)
    max_duration_s: int = Field(default=600, ge=1)
    video_frames: int = Field(default=24, ge=1, le=256)
    explain_top_k: int = Field(default=6, ge=0, le=32)
    max_faces: int = Field(default=4, ge=1, le=16)
    analyze_video_audio: bool = True

    device: str = "auto"
    torch_threads: int = Field(default=0, ge=0)
    workers: int = Field(default=1, ge=1, le=8)
    preload_models: bool = False

    log_level: str = "INFO"
    log_json: bool = False

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def scans_dir(self) -> Path:
        return self.data_dir / "scans"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'dfd.db').as_posix()}"

    def resolved_secret_key(self) -> str:
        """Use the configured key, or create one once and keep it next to the database."""
        if self.secret_key:
            return self.secret_key
        key_file = self.data_dir / "secret.key"
        if not key_file.is_file():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            key_file.write_text(secrets.token_urlsafe(48), encoding="utf-8")
            key_file.chmod(0o600)
        return key_file.read_text(encoding="utf-8").strip()
