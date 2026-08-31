"""Notification dispatcher handling immediate alerts, periodic digest formatting, and multi-server routing."""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.config import settings
from src.analyzers.metrics_aggregator import ContainerStats
from src.notifiers.telegram import TelegramNotifier
from src.notifiers.discord import DiscordNotifier
from src.notifiers.whatsapp import WhatsAppNotifier
from src.notifiers.email import EmailNotifier

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    def __init__(self):
        self.telegram = TelegramNotifier()
        self.discord = DiscordNotifier()
        self.whatsapp = WhatsAppNotifier()
        self.email = EmailNotifier()
        self._last_alert_times: Dict[str, datetime] = {}
        self._suppressed_counts: Dict[str, int] = {}

    def _is_throttled(self, key: str) -> bool:
        """Vérifie si une alerte identique est actuellement sous cooldown anti-spam."""
        now = datetime.now(timezone.utc)
        if key in self._last_alert_times:
            elapsed = (now - self._last_alert_times[key]).total_seconds()
            if elapsed < settings.alert_cooldown_seconds:
                self._suppressed_counts[key] = self._suppressed_counts.get(key, 0) + 1
                return True

        self._last_alert_times[key] = now
        self._suppressed_counts[key] = 0
        return False

    async def send_critical_alert(
        self,
        container_name: str,
        reason: str,
        details: str = "",
        server_name: Optional[str] = None,
        bypass_cooldown: bool = False,
    ):
        """Envoie une alerte critique immédiate sur tous les canaux actifs avec précision du VPS concerné."""
        server = server_name or settings.server_name
        alert_key = f"{server}:{container_name}:{reason[:40]}"
        if not bypass_cooldown and self._is_throttled(alert_key):
            logger.warning(
                f"[AntiSpam] Alerte ignorée pour [{server}] {container_name} (cooldown actif, ignorées: {self._suppressed_counts.get(alert_key, 1)})"
            )
            return

        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

        logger.warning(f"[Alert] Déclenchement alerte critique sur [{server}] {container_name} : {reason}")

        # 1. Telegram (HTML)
        safe_server = TelegramNotifier.escape_html(server)
        safe_container = TelegramNotifier.escape_html(container_name)
        safe_reason = TelegramNotifier.escape_html(reason)
        safe_details = TelegramNotifier.escape_html(details[:800])
        tg_text = (
            f"🚨 <b>[ALERTE CRITIQUE DOKPLOY]</b> 🚨\n\n"
            f"🌐 <b>Serveur / VPS :</b> <code>{safe_server}</code>\n"
            f"📦 <b>Conteneur / App :</b> <code>{safe_container}</code>\n"
            f"⚠️ <b>Incident :</b> {safe_reason}\n"
            f"⏰ <b>Date :</b> {now_str}\n"
        )
        if safe_details:
            tg_text += f"\n📋 <b>Détails & Stacktrace :</b>\n<pre>{safe_details}</pre>\n"
        await self.telegram.send_message(tg_text, parse_mode="HTML")

        # 2. Discord (Rich Embed)
        discord_fields = [
            {"name": "🌐 Serveur / VPS", "value": f"`{server}`", "inline": True},
            {"name": "📦 Conteneur", "value": f"`{container_name}`", "inline": True},
            {"name": "⏰ Date", "value": now_str, "inline": True},
            {"name": "⚠️ Incident", "value": reason, "inline": False},
        ]
        if details:
            discord_fields.append({"name": "📋 Détails", "value": f"```{details[:900]}```", "inline": False})
        await self.discord.send_embed(
            title=f"🚨 Alerte Critique — {server}",
            description=f"Incident détecté sur **{container_name}**.",
            color=0xE74C3C,
            fields=discord_fields,
        )

        # 3. WhatsApp
        wa_text = (
            f"🚨 *[ALERTE CRITIQUE DOKPLOY]* 🚨\n\n"
            f"🌐 *Serveur :* `{server}`\n"
            f"📦 *Conteneur :* `{container_name}`\n"
            f"⚠️ *Incident :* {reason}\n"
            f"⏰ *Date :* {now_str}\n"
        )
        if details:
            wa_text += f"\n📋 *Détails :*\n```{details[:500]}```\n"
        await self.whatsapp.send_message(wa_text)

        # 4. Email
        email_subject = f"🚨 [Dokploy Alert] [{server}] {reason} sur {container_name}"
        email_body_text = f"ALERTE DOKPLOY\n\nServeur: {server}\nConteneur: {container_name}\nIncident: {reason}\nDate: {now_str}\n\nDétails:\n{details}"
        email_body_html = EmailNotifier.build_alert_html(
            title=f"Alerte Critique Dokploy ({server})",
            container_name=f"[{server}] {container_name}",
            reason=reason,
            details=details[:1200],
            timestamp=now_str,
        )
        await self.email.send_email(
            subject=email_subject,
            body_text=email_body_text,
            body_html=email_body_html,
        )

    async def send_uptime_alert(self, target_url: str, reason: str, details: str = ""):
        """Envoie une alerte immédiate lors d'un échec de sonde Uptime HTTP ou expiration SSL."""
        alert_key = f"uptime:{target_url}:{reason[:30]}"
        if self._is_throttled(alert_key):
            return

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        safe_url = TelegramNotifier.escape_html(target_url)
        safe_reason = TelegramNotifier.escape_html(reason)
        safe_details = TelegramNotifier.escape_html(details[:500])

        tg_text = (
            f"🛑 <b>[ALERTE UPTIME / DISPONIBILITÉ]</b> 🛑\n\n"
            f"🔗 <b>Site / API :</b> <code>{safe_url}</code>\n"
            f"⚠️ <b>Incident :</b> {safe_reason}\n"
            f"⏰ <b>Date :</b> {now_str}\n"
        )
        if safe_details:
            tg_text += f"\n📋 <b>Détails :</b>\n<pre>{safe_details}</pre>\n"

        await self.telegram.send_message(tg_text, parse_mode="HTML")
        await self.discord.send_embed(
            title="🛑 Alerte Uptime Site Indisponible",
            description=f"Le site **{target_url}** rencontre une anomalie.",
            color=0xE74C3C,
            fields=[
                {"name": "🔗 URL", "value": target_url, "inline": False},
                {"name": "⚠️ Incident", "value": reason, "inline": False},
                {"name": "⏰ Date", "value": now_str, "inline": True},
            ],
        )

    async def send_server_offline_alert(self, server_name: str, seconds_since: int):
        """Envoie une alerte si un VPS client cesse de transmettre son heartbeat."""
        alert_key = f"server_offline:{server_name}"
        if self._is_throttled(alert_key):
            return

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        mins = seconds_since // 60
        tg_text = (
            f"📡 <b>[SIGNAL PERDU — VPS HORS LIGNE]</b> 📡\n\n"
            f"🌐 <b>Serveur :</b> <code>{TelegramNotifier.escape_html(server_name)}</code>\n"
            f"⚠️ <b>Avertissement :</b> L'agent Sentinel n'a pas répondu depuis plus de {mins} minutes.\n"
            f"⏰ <b>Date :</b> {now_str}\n"
            f"💡 <i>Vérifiez si le serveur VPS est sous tension ou surchargé.</i>"
        )
        await self.telegram.send_message(tg_text, parse_mode="HTML")

    async def send_periodic_digest(
        self,
        stats_grouped: Dict[str, Dict[str, ContainerStats]],
        period_hours: int = 3,
    ):
        """Formate et expédie le rapport de santé global regroupé par serveur VPS."""
        if not stats_grouped:
            logger.info("[Digest] Aucune statistique à envoyer.")
            return

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        total_servers = len(stats_grouped)
        total_containers = sum(len(c_map) for c_map in stats_grouped.values())
        has_critical_issue = False

        tg_message = (
            f"📊 <b>[DOKPLOY SENTINEL — RAPPORT GLOBAL {period_hours}H]</b>\n"
            f"⏰ <b>Horodatage :</b> {now_str}\n"
            f"🌐 <b>Serveurs VPS :</b> <code>{total_servers}</code> | 📦 <b>Conteneurs :</b> <code>{total_containers}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
        )

        containers_flat_list = []

        for s_name, containers_map in sorted(stats_grouped.items()):
            tg_message += f"\n🏢 <b>[{TelegramNotifier.escape_html(s_name)}]</b>\n"

            for name, stats in sorted(containers_map.items()):
                error_rate = stats.error_5xx_rate_percent
                median_lat = f"{stats.median_latency_ms}ms" if stats.median_latency_ms is not None else "N/A"
                p95_lat = f"{stats.p95_latency_ms}ms" if stats.p95_latency_ms is not None else "N/A"

                if error_rate > settings.error_5xx_rate_threshold_percent or len(stats.critical_exceptions) > 0:
                    status = "red"
                    status_icon = "🔴"
                    has_critical_issue = True
                elif stats.count_4xx > 50 or (stats.median_latency_ms and stats.median_latency_ms > 1000):
                    status = "yellow"
                    status_icon = "🟡"
                else:
                    status = "green"
                    status_icon = "🟢"

                containers_flat_list.append({
                    "server": s_name,
                    "name": f"[{s_name}] {name}",
                    "status": status,
                    "status_icon": status_icon,
                    "total_requests": stats.total_requests,
                    "count_2xx": stats.count_2xx,
                    "count_4xx": stats.count_4xx,
                    "count_5xx": stats.count_5xx,
                    "error_rate": error_rate,
                    "median_lat": median_lat,
                    "p95_lat": p95_lat,
                })

                tg_message += (
                    f"  {status_icon} <b>{TelegramNotifier.escape_html(name)}</b> : "
                    f"Req <code>{stats.total_requests}</code> | 5xx <code>{stats.count_5xx}</code> ({error_rate}%) | Méd <code>{median_lat}</code>\n"
                )
                if stats.critical_exceptions:
                    tg_message += f"    └ ❌ <code>{TelegramNotifier.escape_html(stats.critical_exceptions[0][:80])}</code>\n"

        tg_message += (
            f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>État Global :</b> {'⚠️ ATTENTION REQUISE' if has_critical_issue else '✅ TOUS LES SERVEURS SONT NOMINAUX'}"
        )

        await self.telegram.send_message(tg_message, parse_mode="HTML")

        # Discord
        await self.discord.send_embed(
            title=f"📊 DokploySentinel — Rapport Multi-Serveurs ({period_hours}H)",
            description=f"Surveillance de **{total_servers} serveurs** et **{total_containers} conteneurs**.",
            color=0xE74C3C if has_critical_issue else 0x2ECC71,
        )

    async def test_notifications(self, channel: str = "all") -> Dict[str, bool]:
        results = {}
        test_text = "🧪 <b>[DOKPLOY SENTINEL]</b> — Test multi-serveurs réussi !"
        test_plain = "🧪 [DOKPLOY SENTINEL] — Test multi-serveurs réussi !"

        if channel in ("telegram", "all"):
            results["telegram"] = await self.telegram.send_message(test_text, parse_mode="HTML")
        if channel in ("discord", "all"):
            results["discord"] = await self.discord.send_embed(
                title="🧪 Test de Notification DokploySentinel",
                description="Canal Discord opérationnel.",
                color=0x3498DB,
            )
        if channel in ("whatsapp", "all"):
            results["whatsapp"] = await self.whatsapp.send_message(test_plain)
        if channel in ("email", "all"):
            results["email"] = await self.email.send_email(
                subject="🧪 Test DokploySentinel Multi-Serveurs",
                body_text=test_plain,
            )

        return results


dispatcher = NotificationDispatcher()
