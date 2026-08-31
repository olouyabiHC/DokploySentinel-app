"""Notification dispatcher handling immediate alerts, periodic digest formatting, and anti-spam rate limiting."""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

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
        bypass_cooldown: bool = False,
    ):
        """Envoie une alerte immédiate sur tous les canaux actifs avec protection anti-spam."""
        alert_key = f"{container_name}:{reason[:40]}"
        if not bypass_cooldown and self._is_throttled(alert_key):
            logger.warning(
                f"[AntiSpam] Alerte ignorée pour {container_name} (cooldown actif, total ignorées: {self._suppressed_counts.get(alert_key, 1)})"
            )
            return

        now_utc = datetime.now(timezone.utc)
        now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

        logger.warning(f"[Alert] Déclenchement alerte critique pour {container_name} : {reason}")

        # 1. Telegram (HTML)
        safe_container = TelegramNotifier.escape_html(container_name)
        safe_reason = TelegramNotifier.escape_html(reason)
        safe_details = TelegramNotifier.escape_html(details[:800])
        tg_text = (
            f"🚨 <b>[ALERTE CRITIQUE DOKPLOY]</b> 🚨\n\n"
            f"📦 <b>Conteneur :</b> <code>{safe_container}</code>\n"
            f"⚠️ <b>Incident :</b> {safe_reason}\n"
            f"⏰ <b>Date :</b> {now_str}\n"
        )
        if safe_details:
            tg_text += f"\n📋 <b>Détails :</b>\n<pre>{safe_details}</pre>\n"
        await self.telegram.send_message(tg_text, parse_mode="HTML")

        # 2. Discord (Rich Embed)
        discord_fields = [
            {"name": "📦 Conteneur", "value": f"`{container_name}`", "inline": True},
            {"name": "⏰ Date", "value": now_str, "inline": True},
            {"name": "⚠️ Incident", "value": reason, "inline": False},
        ]
        if details:
            discord_fields.append({"name": "📋 Détails", "value": f"```{details[:900]}```", "inline": False})
        await self.discord.send_embed(
            title="🚨 Alerte Critique Dokploy",
            description=f"Un incident critique a été détecté sur **{container_name}**.",
            color=0xE74C3C,  # Rouge vif
            fields=discord_fields,
        )

        # 3. WhatsApp
        wa_text = (
            f"🚨 *[ALERTE CRITIQUE DOKPLOY]* 🚨\n\n"
            f"📦 *Conteneur :* `{container_name}`\n"
            f"⚠️ *Incident :* {reason}\n"
            f"⏰ *Date :* {now_str}\n"
        )
        if details:
            wa_text += f"\n📋 *Détails :*\n```{details[:500]}```\n"
        await self.whatsapp.send_message(wa_text)

        # 4. Email (HTML & Text)
        email_subject = f"🚨 [Dokploy Alert] {reason} sur {container_name}"
        email_body_text = f"ALERTE DOKPLOY\n\nConteneur: {container_name}\nIncident: {reason}\nDate: {now_str}\n\nDétails:\n{details}"
        email_body_html = EmailNotifier.build_alert_html(
            title="Alerte Critique Dokploy",
            container_name=container_name,
            reason=reason,
            details=details[:1200],
            timestamp=now_str,
        )
        await self.email.send_email(
            subject=email_subject,
            body_text=email_body_text,
            body_html=email_body_html,
        )

    async def send_periodic_digest(
        self,
        stats_by_container: Dict[str, ContainerStats],
        period_hours: int = 3,
    ):
        """Formate et expédie le rapport de santé global sur tous les canaux actifs."""
        if not stats_by_container:
            logger.info("[Digest] Aucune statistique à envoyer.")
            return

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        has_critical_issue = False

        # Préparer les données structurées
        containers_summary = []
        for name, stats in sorted(stats_by_container.items()):
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

            containers_summary.append({
                "name": name,
                "status": status,
                "status_icon": status_icon,
                "total_requests": stats.total_requests,
                "count_2xx": stats.count_2xx,
                "count_4xx": stats.count_4xx,
                "count_5xx": stats.count_5xx,
                "error_rate": error_rate,
                "median_lat": median_lat,
                "p95_lat": p95_lat,
                "slow_requests": len(stats.slow_requests),
                "critical_exceptions": stats.critical_exceptions,
            })

        # 1. Telegram
        tg_message = (
            f"📊 <b>[DOKPLOY SENTINEL — RAPPORT {period_hours}H]</b>\n"
            f"⏰ <b>Horodatage :</b> {now_str}\n"
            f"🔍 <b>Conteneurs actifs :</b> {len(containers_summary)}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
        )
        for c in containers_summary:
            tg_message += (
                f"\n{c['status_icon']} <b>{TelegramNotifier.escape_html(c['name'])}</b>\n"
                f"  • Requêtes : <code>{c['total_requests']}</code> | 2xx: <code>{c['count_2xx']}</code> | 4xx: <code>{c['count_4xx']}</code> | 5xx: <code>{c['count_5xx']}</code> ({c['error_rate']}%)\n"
                f"  • Latence : Méd <code>{c['median_lat']}</code> | p95 <code>{c['p95_lat']}</code>\n"
            )
            if c["slow_requests"] > 0:
                tg_message += f"  • ⚠️ Requêtes lentes (>2s) : <code>{c['slow_requests']}</code>\n"
            if c["critical_exceptions"]:
                tg_message += f"  • ❌ Exceptions ({len(c['critical_exceptions'])}) :\n"
                for exc in c["critical_exceptions"][:2]:
                    tg_message += f"    └ <code>{TelegramNotifier.escape_html(exc[:100])}</code>\n"

        tg_message += (
            f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 <b>État Global :</b> {'⚠️ ATTENTION REQUISE' if has_critical_issue else '✅ TOUT FONCTIONNE NORMALEMENT'}"
        )
        await self.telegram.send_message(tg_message, parse_mode="HTML")

        # 2. Discord Embed
        discord_color = 0xE74C3C if has_critical_issue else 0x2ECC71
        discord_fields = []
        for c in containers_summary[:20]:
            val = (
                f"Req: `{c['total_requests']}` | 2xx: `{c['count_2xx']}` | 5xx: `{c['count_5xx']}` ({c['error_rate']}%)\n"
                f"Latence: Méd `{c['median_lat']}` / p95 `{c['p95_lat']}`"
            )
            if c["critical_exceptions"]:
                val += f"\n❌ `{c['critical_exceptions'][0][:80]}`"
            discord_fields.append({
                "name": f"{c['status_icon']} {c['name']}",
                "value": val,
                "inline": False,
            })

        await self.discord.send_embed(
            title=f"📊 DokploySentinel — Rapport de Santé ({period_hours}H)",
            description=f"Rapport consolidé pour **{len(containers_summary)}** conteneurs surveillés.\n"
                        f"**État Global :** {'⚠️ Attention requise' if has_critical_issue else '✅ Nominal'}",
            color=discord_color,
            fields=discord_fields,
        )

        # 3. WhatsApp
        wa_message = (
            f"📊 *[DOKPLOY SENTINEL — RAPPORT {period_hours}H]*\n"
            f"⏰ *Horodatage :* {now_str}\n"
            f"🔍 *Conteneurs :* {len(containers_summary)}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
        )
        for c in containers_summary:
            wa_message += (
                f"\n{c['status_icon']} *{c['name']}*\n"
                f"  • Req: `{c['total_requests']}` | 2xx: `{c['count_2xx']}` | 5xx: `{c['count_5xx']}` ({c['error_rate']}%)\n"
                f"  • Lat: Méd `{c['median_lat']}` | p95 `{c['p95_lat']}`\n"
            )
            if c["critical_exceptions"]:
                wa_message += f"  • ❌ `{c['critical_exceptions'][0][:80]}`\n"

        wa_message += (
            f"\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 *État :* {'⚠️ ATTENTION REQUISE' if has_critical_issue else '✅ NOMINAL'}"
        )
        await self.whatsapp.send_message(wa_message)

        # 4. Email
        email_subj = f"{'🔴 [Attention]' if has_critical_issue else '🟢 [Nominal]'} DokploySentinel — Rapport de Santé ({period_hours}H)"
        email_html = EmailNotifier.build_digest_html(
            period_hours=period_hours,
            timestamp=now_str,
            containers_data=containers_summary,
            has_critical=has_critical_issue,
        )
        await self.email.send_email(
            subject=email_subj,
            body_text=wa_message,
            body_html=email_html,
        )

    async def test_notifications(self, channel: str = "all") -> Dict[str, bool]:
        """Permet de tester l'envoi d'un message test sur un ou tous les canaux."""
        results = {}
        test_text = "🧪 <b>[DOKPLOY SENTINEL]</b> — Ceci est un test de notification réussi !"
        test_plain = "🧪 [DOKPLOY SENTINEL] — Ceci est un test de notification réussi !"

        if channel in ("telegram", "all"):
            results["telegram"] = await self.telegram.send_message(test_text, parse_mode="HTML")

        if channel in ("discord", "all"):
            results["discord"] = await self.discord.send_embed(
                title="🧪 Test de Notification DokploySentinel",
                description="Le canal Discord est correctement configuré et opérationnel.",
                color=0x3498DB,
            )

        if channel in ("whatsapp", "all"):
            results["whatsapp"] = await self.whatsapp.send_message(test_plain)

        if channel in ("email", "all"):
            results["email"] = await self.email.send_email(
                subject="🧪 Test de notification DokploySentinel",
                body_text=test_plain,
                body_html=EmailNotifier.build_alert_html(
                    title="Test de Notification DokploySentinel",
                    container_name="test-service",
                    reason="Vérification de la connectivité SMTP",
                    details="Tous les systèmes de notification fonctionnent normalement.",
                    timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                ),
            )

        return results


dispatcher = NotificationDispatcher()
