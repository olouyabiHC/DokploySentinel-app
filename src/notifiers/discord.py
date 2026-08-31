"""Discord Webhook notifier for DokploySentinel."""

import logging
import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self):
        self.webhook_url = settings.discord_webhook_url
        self.enabled = settings.discord_enabled and bool(self.webhook_url)

    async def send_message(self, text: str) -> bool:
        if not self.enabled:
            return False

        payload = {"content": text}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                if 200 <= response.status_code < 300:
                    return True
                logger.error(f"[Discord] Erreur webhook : HTTP {response.status_code} — {response.text}")
                return False
        except Exception as e:
            logger.error(f"[Discord] Exception lors de l'envoi : {e}")
            return False
