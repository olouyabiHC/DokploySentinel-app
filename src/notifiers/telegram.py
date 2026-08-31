"""Telegram Bot notifier for DokploySentinel with robust HTML formatting, inline keyboards, and webhook support."""

import html
import logging
from typing import Dict, List, Optional
import httpx

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

    async def send_message(
        self,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[dict] = None,
        chat_id: Optional[str] = None,
    ) -> bool:
        """Envoie un message formaté avec support optionnel de boutons interactifs (Inline Keyboard)."""
        if not self.enabled and not chat_id:
            return False

        target_chat = chat_id or self.chat_id
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

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
                    "chat_id": target_chat,
                    "text": text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<pre>", "").replace("</pre>", ""),
                    "disable_web_page_preview": True,
                }
                if reply_markup:
                    fallback_payload["reply_markup"] = reply_markup
                fallback_resp = await client.post(url, json=fallback_payload)
                return fallback_resp.status_code == 200

        except Exception as e:
            logger.error(f"[Telegram] Exception lors de l'envoi : {e}")
            return False

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Accuse réception d'un clic de bouton interactif sur Telegram."""
        if not self.bot_token:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"[Telegram] Erreur answerCallbackQuery : {e}")
            return False

    async def edit_message_text(
        self,
        chat_id: str | int,
        message_id: int,
        text: str,
        reply_markup: Optional[dict] = None,
        parse_mode: str = "HTML",
    ) -> bool:
        """Modifie un message existant (par exemple après un clic sur un bouton)."""
        if not self.bot_token:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                return resp.status_code == 200
        except Exception as e:
            logger.debug(f"[Telegram] Erreur editMessageText : {e}")
            return False

    async def set_webhook(self, webhook_url: str, secret_token: Optional[str] = None) -> bool:
        """Configure le Webhook officiel auprès des serveurs Telegram."""
        if not self.bot_token:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/setWebhook"
        payload = {
            "url": webhook_url,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": False,
        }
        if secret_token:
            payload["secret_token"] = secret_token

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200 and resp.json().get("ok"):
                    logger.info(f"[Telegram] Webhook configuré avec succès sur : {webhook_url}")
                    return True
                logger.warning(f"[Telegram] Échec configuration webhook ({resp.status_code}) : {resp.text}")
                return False
        except Exception as e:
            logger.error(f"[Telegram] Erreur setWebhook : {e}")
            return False

    async def delete_webhook(self) -> bool:
        """Supprime le Webhook Telegram pour repasser en mode passif si nécessaire."""
        if not self.bot_token:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/deleteWebhook"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url)
                return resp.status_code == 200 and resp.json().get("ok")
        except Exception as e:
            logger.error(f"[Telegram] Erreur deleteWebhook : {e}")
            return False
