"""Configuration module using Pydantic Settings."""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "DokploySentinel"
    app_env: str = "production"
    debug: bool = False
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    secret_key: str = "change-this-secret-key"

    # Docker & Dokploy
    docker_socket_path: str = "unix://var/run/docker.sock"
    monitored_container_patterns: str = ""
    ignored_container_patterns: str = "pgbouncer,postgres,redis,dokploy-traefik"

    # Periodic Digest & Thresholds
    digest_interval_hours: int = 3
    latency_alert_threshold_ms: int = 2000
    error_5xx_rate_threshold_percent: float = 5.0

    # Telegram
    telegram_enabled: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # Discord
    discord_enabled: bool = False
    discord_webhook_url: Optional[str] = None

    # WhatsApp
    whatsapp_enabled: bool = False
    whatsapp_api_url: Optional[str] = None
    whatsapp_api_key: Optional[str] = None
    whatsapp_instance: Optional[str] = None
    whatsapp_recipient_number: Optional[str] = None

    # Email
    email_enabled: bool = False
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    email_from: Optional[str] = None
    email_to: Optional[str] = None

    @property
    def monitored_patterns_list(self) -> List[str]:
        if not self.monitored_container_patterns:
            return []
        return [p.strip().lower() for p in self.monitored_container_patterns.split(",") if p.strip()]

    @property
    def ignored_patterns_list(self) -> List[str]:
        if not self.ignored_container_patterns:
            return []
        return [p.strip().lower() for p in self.ignored_container_patterns.split(",") if p.strip()]


settings = Settings()
