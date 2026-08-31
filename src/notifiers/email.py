"""Email (SMTP) Notifier for DokploySentinel with HTML templates."""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional
import aiosmtplib

from src.config import settings

logger = logging.getLogger(__name__)


class EmailNotifier:
    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.user = settings.smtp_user
        self.password = settings.smtp_password
        self.email_from = settings.email_from or self.user
        self.email_to = settings.email_to
        self.use_tls = settings.smtp_use_tls
        self.use_ssl = settings.smtp_use_ssl
        self.enabled = (
            settings.email_enabled
            and bool(self.host)
            and bool(self.email_to)
        )

    def _get_recipients(self) -> List[str]:
        if not self.email_to:
            return []
        return [r.strip() for r in self.email_to.split(",") if r.strip()]

    async def send_email(self, subject: str, body_text: str, body_html: Optional[str] = None) -> bool:
        """Envoie un email asynchrone via SMTP avec fallback texte et corps HTML."""
        if not self.enabled:
            return False

        recipients = self._get_recipients()
        if not recipients:
            return False

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.email_from
        msg["To"] = ", ".join(recipients)

        # Partie texte brut
        part_text = MIMEText(body_text, "plain", "utf-8")
        msg.attach(part_text)

        # Partie HTML si disponible
        if body_html:
            part_html = MIMEText(body_html, "html", "utf-8")
            msg.attach(part_html)

        try:
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                start_tls=self.use_tls and not self.use_ssl,
                use_tls=self.use_ssl,
                timeout=15,
            )
            logger.info(f"[Email] Message envoyé avec succès à {msg['To']} (Sujet: {subject})")
            return True
        except Exception as e:
            logger.error(f"[Email] Erreur lors de l'envoi SMTP : {e}")
            return False

    @staticmethod
    def build_alert_html(title: str, container_name: str, reason: str, details: str, timestamp: str) -> str:
        """Génère un email HTML moderne pour une alerte d'urgence."""
        details_block = (
            f"""
            <div style="margin-top: 15px; background: #1e1e1e; color: #ff8080; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 13px; overflow-x: auto; white-space: pre-wrap;">
                {details}
            </div>
            """
            if details
            else ""
        )

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 20px;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                    <td align="center">
                        <table width="600" style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden;">
                            <tr style="background-color: #d32f2f; color: #ffffff;">
                                <td style="padding: 18px 24px;">
                                    <h2 style="margin: 0; font-size: 20px; font-weight: 600;">🚨 {title}</h2>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 24px;">
                                    <p style="margin: 0 0 10px 0; font-size: 15px;"><strong>Conteneur / Application :</strong> <code style="background: #eee; padding: 2px 6px; border-radius: 4px;">{container_name}</code></p>
                                    <p style="margin: 0 0 10px 0; font-size: 15px;"><strong>Incident :</strong> <span style="color: #d32f2f; font-weight: bold;">{reason}</span></p>
                                    <p style="margin: 0 0 15px 0; font-size: 13px; color: #777;"><strong>Horodatage :</strong> {timestamp}</p>
                                    {details_block}
                                    <div style="margin-top: 25px; border-top: 1px solid #eee; padding-top: 15px; font-size: 12px; color: #888; text-align: center;">
                                        DokploySentinel — Observabilité & Alerting Automatisé
                                    </div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

    @staticmethod
    def build_digest_html(period_hours: int, timestamp: str, containers_data: list, has_critical: bool) -> str:
        """Génère un email HTML moderne pour le rapport périodique."""
        status_color = "#d32f2f" if has_critical else "#2e7d32"
        status_banner = (
            "⚠️ ATTENTION REQUISE SUR CERTAINS CONTENEURS"
            if has_critical
            else "✅ TOUS LES SYSTÈMES SONT NOMINAUX"
        )

        rows_html = ""
        for c in containers_data:
            badge_color = "#2e7d32" if c["status"] == "green" else ("#f57c00" if c["status"] == "yellow" else "#d32f2f")
            rows_html += f"""
            <tr style="border-bottom: 1px solid #eee;">
                <td style="padding: 12px 8px; font-weight: bold;">
                    <span style="display: inline-block; width: 10px; height: 10px; border-radius: 50%; background-color: {badge_color}; margin-right: 6px;"></span>
                    {c["name"]}
                </td>
                <td style="padding: 12px 8px; text-align: center;">{c["total_requests"]}</td>
                <td style="padding: 12px 8px; text-align: center; color: #2e7d32;">{c["count_2xx"]}</td>
                <td style="padding: 12px 8px; text-align: center; color: #f57c00;">{c["count_4xx"]}</td>
                <td style="padding: 12px 8px; text-align: center; color: #d32f2f; font-weight: bold;">{c["count_5xx"]} ({c["error_rate"]}%)</td>
                <td style="padding: 12px 8px; text-align: center;">{c["median_lat"]}</td>
                <td style="padding: 12px 8px; text-align: center;">{c["p95_lat"]}</td>
            </tr>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f8; margin: 0; padding: 20px;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                    <td align="center">
                        <table width="700" style="background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); overflow: hidden;">
                            <tr style="background-color: {status_color}; color: #ffffff;">
                                <td style="padding: 18px 24px;">
                                    <h2 style="margin: 0; font-size: 20px; font-weight: 600;">📊 DokploySentinel — Rapport de Santé ({period_hours}H)</h2>
                                    <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">{timestamp}</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 20px 24px;">
                                    <div style="background-color: #f8f9fa; border-left: 4px solid {status_color}; padding: 10px 15px; margin-bottom: 20px; font-weight: 600;">
                                        {status_banner}
                                    </div>
                                    <table width="100%" style="border-collapse: collapse; font-size: 14px;">
                                        <thead>
                                            <tr style="background-color: #f1f3f5; color: #495057; font-size: 12px; text-transform: uppercase;">
                                                <th style="padding: 10px 8px; text-align: left;">Conteneur</th>
                                                <th style="padding: 10px 8px; text-align: center;">Req.</th>
                                                <th style="padding: 10px 8px; text-align: center;">2xx</th>
                                                <th style="padding: 10px 8px; text-align: center;">4xx</th>
                                                <th style="padding: 10px 8px; text-align: center;">5xx</th>
                                                <th style="padding: 10px 8px; text-align: center;">Méd.</th>
                                                <th style="padding: 10px 8px; text-align: center;">p95</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {rows_html}
                                        </tbody>
                                    </table>
                                    <div style="margin-top: 25px; border-top: 1px solid #eee; padding-top: 15px; font-size: 12px; color: #888; text-align: center;">
                                        DokploySentinel — Rapport automatique généré toutes les {period_hours} heures
                                    </div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
