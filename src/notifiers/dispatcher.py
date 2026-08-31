"""Notification dispatcher handling immediate alerts and periodic digest formatting."""

import logging
from datetime import datetime, timezone
from typing import Dict, List

from src.analyzers.metrics_aggregator import ContainerStats
from src.notifiers.telegram import TelegramNotifier
from src.notifiers.discord import DiscordNotifier

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    def __init__(self):
        self.telegram = TelegramNotifier()
        self.discord = DiscordNotifier()

    async def send_critical_alert(self, container_name: str, reason: str, details: str = ""):
        """Envoie une alerte immédiate en temps réel sur les canaux configurés."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        message = (
            f"🚨 *[ALERTE CRITIQUE DOKPLOY]* 🚨\n\n"
            f"📦 *Conteneur / Projet :* `{container_name}`\n"
            f"⚠️ *Incident :* {reason}\n"
            f"⏰ *Date :* {now_str}\n"
        )
        if details:
            message += f"\n📋 *Détails :*\n```\n{details[:800]}\n```\n"

        logger.warning(f"[Alert] Envoi alerte critique pour {container_name} : {reason}")
        await self.telegram.send_message(message)
        await self.discord.send_message(message.replace("*", "**"))

    async def send_periodic_digest(self, stats_by_container: Dict[str, ContainerStats], period_hours: int = 3):
        """Formate et envoie le digest de santé global toutes les 2h ou 3h."""
        if not stats_by_container:
            logger.info("[Digest] Aucune statistique à envoyer.")
            return

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        
        # En-tête du Digest
        message = (
            f"📊 *[DOKPLOY SENTINEL — RAPPORT {period_hours}H]*\n"
            f"⏰ *Horodatage :* {now_str}\n"
            f"🔍 *Projets / Conteneurs actifs :* {len(stats_by_container)}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
        )

        has_critical_issue = False

        for name, stats in sorted(stats_by_container.items()):
            if stats.total_requests == 0 and not stats.critical_exceptions:
                continue

            error_rate = stats.error_5xx_rate_percent
            median_lat = f"{stats.median_latency_ms}ms" if stats.median_latency_ms is not None else "N/A"
            p95_lat = f"{stats.p95_latency_ms}ms" if stats.p95_latency_ms is not None else "N/A"
            
            # Statut visuel
            if error_rate > 5.0 or len(stats.critical_exceptions) > 0:
                status_icon = "🔴"
                has_critical_issue = True
            elif stats.count_4xx > 50 or (stats.median_latency_ms and stats.median_latency_ms > 1000):
                status_icon = "🟡"
            else:
                status_icon = "🟢"

            message += (
                f"\n{status_icon} *{name}*\n"
                f"  • Requêtes totales : `{stats.total_requests}`\n"
                f"  • 2xx (Succès) : `{stats.count_2xx}` | 4xx : `{stats.count_4xx}` | 5xx : `{stats.count_5xx}` ({error_rate}%)\n"
                f"  • Latence : médiane `{median_lat}` | p95 `{p95_lat}`\n"
            )

            if stats.slow_requests:
                message += f"  • ⚠️ Requêtes lentes (>2s) : `{len(stats.slow_requests)}`\n"

            if stats.critical_exceptions:
                message += f"  • ❌ Exceptions détectées : `{len(stats.critical_exceptions)}`\n"
                for exc in stats.critical_exceptions[:2]:
                    clean_exc = exc.replace('`', "'")[:120]
                    message += f"    └ `{clean_exc}`\n"

        message += (
            f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *État Global :* {'⚠️ ATTENTION REQUISE' if has_critical_issue else '✅ TOUT FONCTIONNE NORMALEMENT'}"
        )

        logger.info("[Digest] Envoi du digest périodique...")
        await self.telegram.send_message(message)
        await self.discord.send_message(message.replace("*", "**"))


dispatcher = NotificationDispatcher()
