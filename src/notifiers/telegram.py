"""Telegram Bot notifier for DokploySentinel with robust HTML formatting and plain text fallback."""

import html
import logging
import httpx
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self):
        self.bot_token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.enabled = settings.telegram_enabled and bool(self.bot_token) and bool(self.chat_id)

    @staticmethod
    def escape_html(text: str) -> str:
        """Échappe le texte pour une utilisation sûre dans Telegram en mode HTML."""
        return html.escape(text or "", quote=False)

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        if not self.enabled:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    return True

                logger.warning(
                    f"[Telegram] Échec envoi formaté ({response.status_code}) : {response.text}. Tentative en texte brut..."
                )
                # Tentative de secours en texte brut (sans parse_mode)
                fallback_payload = {
                    "chat_id": self.chat_id,
                    "text": text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<pre>", "").replace("</pre>", ""),
                    "disable_web_page_preview": True,
                }
                fallback_resp = await client.post(url, json=fallback_payload)
                return fallback_resp.status_code == 200

        except Exception as e:
            logger.error(f"[Telegram] Exception lors de l'envoi : {e}")
            return False
