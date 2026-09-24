"""
UrbanSense AI — Centralised Backend Configuration
==================================================
All configuration is read from environment variables.
No secrets or credentials are hard-coded here.

Defaults are safe for local development only.
Production values MUST come from environment / secrets manager.
"""

from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql://urbansense:urbansense_dev@localhost:5432/urbansense"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # MinIO / Object storage
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "urbansense"
    minio_root_password: str = "change_me"
    minio_bucket_evidence: str = "urbansense-evidence"
    minio_use_ssl: bool = False

    # MQTT
    mqtt_broker_host: str = "localhost"
    mqtt_broker_port: int = 1883

    # Map matching — PROTOTYPE
    # DECISION_REQUIRED: replace with real map-matching engine in production
    map_match_prototype_segment_id: str = "SEG-001"
    map_match_prototype_confidence: float = 0.85
    map_match_hint_radius_m: float = 100.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()