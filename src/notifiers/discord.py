"""Discord Webhook notifier for DokploySentinel with Rich Embed support."""

import logging
from typing import Any, Dict, List, Optional
import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self):
        self.webhook_url = settings.discord_webhook_url
        self.enabled = settings.discord_enabled and bool(self.webhook_url)

    async def send_message(self, text: str) -> bool:
        """Envoie un message textuel simple via webhook Discord."""
        if not self.enabled:
            return False

        payload = {"content": text[:2000]}

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

    async def send_embed(
        self,
        title: str,
        description: str,
        color: int = 0x3498DB,
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: str = "DokploySentinel",
    ) -> bool:
        """Envoie un message avec Embed enrichi et stylisé (couleurs, champs alignés)."""
        if not self.enabled:
            return False

        embed = {
            "title": title[:256],
            "description": description[:4096],
            "color": color,
            "footer": {"text": footer},
        }
        if fields:
            embed["fields"] = fields[:25]

        payload = {"embeds": [embed]}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.webhook_url, json=payload)
                if 200 <= response.status_code < 300:
                    return True
                logger.error(f"[Discord] Erreur webhook embed : HTTP {response.status_code} — {response.text}")
                return False
        except Exception as e:
            logger.error(f"[Discord] Exception lors de l'envoi embed : {e}")
            return False
