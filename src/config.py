"""Configuration module using Pydantic Settings for DokploySentinel Hub & Agent."""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application & Hub Identifiers
    app_name: str = "DokploySentinel"
    app_env: str = "production"
    server_name: str = "VPS-Principal-Lekyn"
    debug: bool = False
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    secret_key: str = "dokploy-sentinel-secret-2026-secure-key"

    # Docker & Dokploy Local
    docker_socket_path: str = "unix://var/run/docker.sock"
    monitored_container_patterns: str = ""
    ignored_container_patterns: str = "pgbouncer,postgres,redis,dokploy-traefik,dokploy-sentinel"

    # Periodic Digest & Alert Thresholds
    digest_interval_hours: int = 3
    latency_alert_threshold_ms: int = 2000
    error_5xx_rate_threshold_percent: float = 5.0
    memory_alert_threshold_percent: float = 90.0
    cpu_alert_threshold_percent: float = 95.0
    alert_cooldown_seconds: int = 300

    # Multi-Server Agent & Uptime Probing
    agent_heartbeat_timeout_seconds: int = 180
    monitored_http_targets: str = ""
    uptime_probe_interval_seconds: int = 60

    # Telegram Bot & Interactive Webhook
    telegram_enabled: bool = False
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_webhook_secret: str = "dokploy-telegram-webhook-secret-token"
    telegram_webhook_url: Optional[str] = None

    # AI Root-Cause Analysis (Gemini / OpenAI / Heuristic)
    ai_analysis_enabled: bool = True
    gemini_api_key: Optional[str] = None
    ai_api_key: Optional[str] = None

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
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
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

    @property
    def http_targets_list(self) -> List[str]:
        if not self.monitored_http_targets:
            return []
        return [url.strip() for url in self.monitored_http_targets.split(",") if url.strip()]


settings = Settings()
