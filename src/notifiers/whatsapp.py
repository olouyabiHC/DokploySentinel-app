"""WhatsApp Notifier for DokploySentinel supporting Evolution API and standard WhatsApp Webhooks."""

import logging
from typing import Optional
import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class WhatsAppNotifier:
    def __init__(self):
        self.api_url = settings.whatsapp_api_url.rstrip("/") if settings.whatsapp_api_url else None
        self.api_key = settings.whatsapp_api_key
        self.instance = settings.whatsapp_instance
        self.recipient = settings.whatsapp_recipient_number
        self.enabled = (
            settings.whatsapp_enabled
            and bool(self.api_url)
            and bool(self.recipient)
        )

    async def send_message(self, text: str) -> bool:
        """Envoie un message WhatsApp via l'API configurée (ex: Evolution API)."""
        if not self.enabled:
            return False

        # Si instance spécifiée, formater pour Evolution API v1/v2
        if self.instance:
            endpoint = f"{self.api_url}/message/sendText/{self.instance}"
            payload = {
                "number": self.recipient,
                "options": {
                    "delay": 500,
                    "presence": "composing",
                    "linkPreview": False,
                },
                "text": text,
            }
        else:
            # Endpoint générique / webhook WhatsApp
            endpoint = self.api_url
            payload = {
                "number": self.recipient,
                "recipient": self.recipient,
                "text": text,
                "message": text,
            }

        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["apikey"] = self.api_key
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(endpoint, json=payload, headers=headers)
                if 200 <= response.status_code < 300:
                    logger.info(f"[WhatsApp] Message envoyé avec succès au {self.recipient}")
                    return True
                logger.error(
                    f"[WhatsApp] Échec envoi : HTTP {response.status_code} — {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"[WhatsApp] Erreur de communication avec l'API : {e}")
            return False
