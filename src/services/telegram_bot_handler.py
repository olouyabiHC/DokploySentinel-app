"""Interactive Telegram Bot Handler for DokploySentinel 2.0 (Commands & Callbacks)."""

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.config import settings
from src.analyzers.metrics_aggregator import metrics_aggregator
from src.collectors.docker_collector import docker_collector
from src.collectors.uptime_prober import uptime_prober
from src.notifiers.telegram import TelegramNotifier
from src.services.mutes_manager import mutes_manager
from src.services.ai_analyzer import ai_analyzer

logger = logging.getLogger(__name__)


class TelegramBotHandler:
    def __init__(self):
        self.telegram = TelegramNotifier()

    async def process_update(self, update: dict) -> bool:
        """Point d'entrée principal pour traiter les événements reçus via Webhook Telegram."""
        try:
            # 1. Traitement des commandes et messages texte
            if "message" in update:
                message = update["message"]
                text = message.get("text", "")
                chat_id = str(message.get("chat", {}).get("id", ""))
                sender = message.get("from", {}).get("username") or message.get("from", {}).get("first_name", "Utilisateur")

                # Vérification d'autorisation
                if not self._is_authorized_chat(chat_id):
                    logger.warning(f"[TelegramBot] Message rejeté depuis un chat non autorisé : {chat_id}")
                    return False

                if text.startswith("/"):
                    await self._handle_command(text, chat_id, sender)
                    return True

            # 2. Traitement des clics sur les boutons interactifs (Callback Queries)
            elif "callback_query" in update:
                cb = update["callback_query"]
                cb_id = cb.get("id")
                data = cb.get("data", "")
                message = cb.get("message", {})
                chat_id = str(message.get("chat", {}).get("id", ""))
                message_id = message.get("message_id")
                sender = cb.get("from", {}).get("username") or cb.get("from", {}).get("first_name", "Utilisateur")

                if not self._is_authorized_chat(chat_id):
                    return False

                await self._handle_callback_query(cb_id, data, chat_id, message_id, message.get("text", ""), sender)
                return True

        except Exception as e:
            logger.error(f"[TelegramBot] Erreur lors du traitement de l'update Telegram : {e}", exc_info=True)
            return False

        return False

    def _is_authorized_chat(self, chat_id: str) -> bool:
        """Vérifie si le message provient du groupe de notification autorisé."""
        if not settings.telegram_chat_id:
            return True
        configured_id = str(settings.telegram_chat_id).strip()
        # Correspondance exacte ou avec/sans préfixe -100
        return (
            chat_id == configured_id
            or chat_id.replace("-100", "") == configured_id.replace("-100", "")
            or chat_id.endswith(configured_id[-9:])
        )

    async def _handle_command(self, text: str, chat_id: str, sender: str):
        """Parse et exécute les commandes Telegram."""
        parts = text.strip().split()
        command = parts[0].lower().split("@")[0]  # Supporte /status@BotName
        args = parts[1:]

        logger.info(f"[TelegramBot] Commande reçue de @{sender} : {text}")

        if command in ("/start", "/help"):
            await self._cmd_help(chat_id)
        elif command == "/status":
            await self._cmd_status(chat_id)
        elif command == "/servers":
            await self._cmd_servers(chat_id)
        elif command == "/containers":
            await self._cmd_containers(chat_id)
        elif command == "/mute":
            await self._cmd_mute(args, chat_id)
        elif command == "/unmute":
            await self._cmd_unmute(args, chat_id)
        elif command == "/mutes":
            await self._cmd_mutes_list(chat_id)
        elif command == "/logs":
            await self._cmd_logs(args, chat_id)
        elif command == "/restart":
            await self._cmd_restart(args, chat_id)
        elif command == "/digest":
            await self._cmd_digest(chat_id)
        elif command == "/ai":
            await self._cmd_ai(args, chat_id)
        else:
            await self.telegram.send_message(
                f"❓ Commande inconnue : <code>{TelegramNotifier.escape_html(command)}</code>\n"
                f"Tapez /help pour voir la liste des commandes disponibles.",
                chat_id=chat_id,
            )

    # ── Commandes Utilisateurs ──────────────────────────────────────────────────

    async def _cmd_help(self, chat_id: str):
        text = (
            "🛡️ <b>[DOKPLOY SENTINEL 2.0 — MENU INTERACTIF]</b> 🛡️\n\n"
            "Voici les commandes que vous pouvez utiliser directement dans ce groupe :\n\n"
            "📊 <b>Surveillance & Métriques :</b>\n"
            "• /status : Vue d'ensemble en direct de tous les VPS et de la santé globale\n"
            "• /servers : Liste des serveurs VPS connectés et charge hôte (CPU/RAM/Disque)\n"
            "• /containers : État détaillé de tous les conteneurs sous surveillance\n"
            "• /digest : Déclenche immédiatement le rapport de santé consolidé\n\n"
            "🔇 <b>Gestion des Filtres & Sourdines :</b>\n"
            "• <code>/mute &lt;nom_ou_motif&gt; [durée]</code> : Coupe les alertes (ex: <code>/mute wordpress 2h</code> ou <code>/mute all 30m</code>)\n"
            "• <code>/unmute &lt;nom_ou_motif&gt;</code> : Réactive les alertes\n"
            "• /mutes : Affiche les règles de sourdine actuellement actives\n\n"
            "⚡ <b>Actions & Diagnostics :</b>\n"
            "• <code>/logs &lt;nom_conteneur&gt;</code> : Récupère les 25 dernières lignes de logs\n"
            "• <code>/restart &lt;nom_conteneur&gt;</code> : Redémarre un conteneur à distance\n"
            "• <code>/ai &lt;nom_conteneur&gt;</code> : Analyse intelligente par IA des dernières erreurs\n"
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "📊 Statut Global", "callback_data": "cmd:status"},
                    {"text": "🏢 Serveurs VPS", "callback_data": "cmd:servers"},
                ],
                [
                    {"text": "🔇 Muter WordPress (2h)", "callback_data": "mute:wordpress:120"},
                    {"text": "📋 Liste des Mutes", "callback_data": "cmd:mutes"},
                ],
                [
                    {"text": "📑 Générer Rapport", "callback_data": "cmd:digest"},
                ],
            ]
        }
        await self.telegram.send_message(text, reply_markup=reply_markup, chat_id=chat_id)

    async def _cmd_status(self, chat_id: str):
        servers = metrics_aggregator.get_servers_overview()
        uptime_data = uptime_prober.get_overview()

        total_servers = len(servers)
        online_servers = sum(1 for s in servers if s.get("status") == "online")
        total_containers = sum(s.get("containers_count", 0) for s in servers)

        probes = uptime_data.get("targets", [])
        up_probes = sum(1 for p in probes if p.get("status") == "UP")

        text = (
            "📊 <b>[ÉTAT EN DIRECT DU CLUSTER DOKPLOY]</b>\n"
            f"⏰ <b>Horodatage :</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 <b>Serveurs VPS :</b> <code>{online_servers}/{total_servers} en ligne</code>\n"
            f"📦 <b>Conteneurs Actifs :</b> <code>{total_containers}</code>\n"
            f"🔗 <b>Sondes Uptime HTTP :</b> <code>{up_probes}/{len(probes)} Disponibles</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        for s in servers:
            icon = "🟢" if s.get("status") == "online" else "🔴"
            text += (
                f"{icon} <b>{TelegramNotifier.escape_html(s['server_name'])}</b>\n"
                f"  └ CPU: <code>{s.get('host_cpu_percent', 0)}%</code> | RAM: <code>{s.get('host_memory_percent', 0)}%</code> | Disque: <code>{s.get('host_disk_percent', 0)}%</code> | Apps: <code>{s.get('containers_count', 0)}</code>\n"
            )

        if probes:
            text += "\n🔗 <b>Sondes Uptime & SSL :</b>\n"
            for p in probes:
                p_icon = "🟢" if p.get("status") == "UP" else "🔴"
                ssl_text = f"SSL: {p.get('ssl_days_left')}j" if p.get("ssl_days_left") is not None else "SSL: N/A"
                text += f"  {p_icon} <code>{p['url']}</code> ({p.get('latency_ms', 0)}ms, {ssl_text})\n"

        await self.telegram.send_message(text, chat_id=chat_id)

    async def _cmd_servers(self, chat_id: str):
        servers = metrics_aggregator.get_servers_overview()
        if not servers:
            await self.telegram.send_message("ℹ️ Aucun serveur VPS n'a encore été détecté.", chat_id=chat_id)
            return

        text = "🏢 <b>[LISTE DES SERVEURS VPS CONNECTÉS]</b>\n\n"
        for s in servers:
            status_icon = "🟢" if s.get("status") == "online" else "🔴"
            last_seen = f"{s.get('seconds_since_last_seen', 0)}s"
            text += (
                f"{status_icon} <b>{TelegramNotifier.escape_html(s['server_name'])}</b> ({s.get('status', 'unknown')})\n"
                f"  • Conteneurs : <code>{s.get('containers_count', 0)}</code>\n"
                f"  • Charge CPU : <code>{s.get('host_cpu_percent', 0)}%</code>\n"
                f"  • Mémoire RAM : <code>{s.get('host_memory_percent', 0)}%</code>\n"
                f"  • Espace Disque : <code>{s.get('host_disk_percent', 0)}%</code>\n"
                f"  • Dernier Heartbeat : il y a {last_seen}\n\n"
            )
        await self.telegram.send_message(text, chat_id=chat_id)

    async def _cmd_containers(self, chat_id: str):
        stats_grouped = metrics_aggregator.get_stats_grouped_by_server()
        if not stats_grouped:
            await self.telegram.send_message("ℹ️ Aucun conteneur surveillé pour le moment.", chat_id=chat_id)
            return

        text = "📦 <b>[CONTENEURS SOUS SURVEILLANCE]</b>\n"
        for server, c_map in stats_grouped.items():
            text += f"\n🏢 <b>{TelegramNotifier.escape_html(server)} :</b>\n"
            for c_name, stat in list(c_map.items())[:15]:
                muted = " 🔇" if mutes_manager.is_muted(c_name, server) else ""
                health_icon = "🟢" if stat.health_status == "healthy" else ("🟡" if stat.health_status == "unknown" else "🔴")
                text += f"  {health_icon} <code>{TelegramNotifier.escape_html(c_name)}</code> (RAM: {round(stat.max_memory_mb, 1)}MB){muted}\n"

        await self.telegram.send_message(text, chat_id=chat_id)

    async def _cmd_mute(self, args: List[str], chat_id: str):
        if not args:
            await self.telegram.send_message(
                "⚠️ Format requis : <code>/mute &lt;motif&gt; [durée]</code>\n"
                "Exemples :\n"
                "• <code>/mute wordpress 2h</code> (mute 2 heures)\n"
                "• <code>/mute association 30m</code> (mute 30 minutes)\n"
                "• <code>/mute all 1h</code> (mute toutes les alertes pendant 1h)",
                chat_id=chat_id,
            )
            return

        pattern = args[0]
        duration_min = None
        if len(args) > 1:
            duration_min = self._parse_duration(args[1])

        rule = mutes_manager.mute(pattern=pattern, duration_minutes=duration_min, reason="Commande Telegram")
        dur_text = f"pendant <b>{rule.remaining_minutes} minutes</b>" if duration_min else "<b>de manière permanente</b>"

        text = (
            f"🔇 <b>[SOURDINE ACTIVÉE]</b>\n\n"
            f"Le motif <code>{TelegramNotifier.escape_html(pattern)}</code> est désormais en sourdine {dur_text}.\n"
            f"Toutes les alertes correspondantes seront ignorées."
        )
        await self.telegram.send_message(text, chat_id=chat_id)

    async def _cmd_unmute(self, args: List[str], chat_id: str):
        if not args:
            await self.telegram.send_message("⚠️ Précisez le motif à réactiver : <code>/unmute &lt;motif&gt;</code>", chat_id=chat_id)
            return

        pattern = args[0]
        if mutes_manager.unmute(pattern):
            await self.telegram.send_message(f"🔊 Sourdine levée pour <code>{TelegramNotifier.escape_html(pattern)}</code>. Surveillance réactivée !", chat_id=chat_id)
        else:
            await self.telegram.send_message(f"ℹ️ Aucune règle de sourdine active trouvée pour <code>{TelegramNotifier.escape_html(pattern)}</code>.", chat_id=chat_id)

    async def _cmd_mutes_list(self, chat_id: str):
        mutes = mutes_manager.get_active_mutes()
        if not mutes:
            await self.telegram.send_message("🔊 <b>Aucune sourdine active.</b> Tous les conteneurs sont surveillés normalement.", chat_id=chat_id)
            return

        text = "🔇 <b>[RÈGLES DE SOURDINE ACTIVES]</b>\n\n"
        for m in mutes:
            rem = f"{m['remaining_minutes']} min restantes" if m["remaining_minutes"] is not None else "Permanente"
            text += f"• <code>{TelegramNotifier.escape_html(m['pattern'])}</code> ➔ <i>{rem}</i>\n"

        text += "\nPour réactiver : <code>/unmute &lt;motif&gt;</code>"
        await self.telegram.send_message(text, chat_id=chat_id)

    async def _cmd_logs(self, args: List[str], chat_id: str):
        if not args:
            await self.telegram.send_message("⚠️ Précisez le nom du conteneur : <code>/logs &lt;nom_conteneur&gt;</code>", chat_id=chat_id)
            return

        target = args[0]
        lines_count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 25

        if not docker_collector.client:
            await self.telegram.send_message("❌ Socket Docker non accessible sur le Hub.", chat_id=chat_id)
            return

        loop = asyncio.get_running_loop()
        try:
            containers = await loop.run_in_executor(None, docker_collector.client.containers.list, True)
            matching = [c for c in containers if target.lower() in c.name.lower()]

            if not matching:
                await self.telegram.send_message(f"❌ Aucun conteneur trouvé correspondant à <code>{TelegramNotifier.escape_html(target)}</code>.", chat_id=chat_id)
                return

            c = matching[0]
            raw_logs = await loop.run_in_executor(
                None,
                lambda: c.logs(tail=lines_count, timestamps=False).decode("utf-8", errors="replace"),
            )

            snippet = TelegramNotifier.escape_html(raw_logs[-3000:] if raw_logs.strip() else "(Aucun log récent)")
            text = (
                f"📋 <b>Derniers logs de <code>{TelegramNotifier.escape_html(c.name)}</code> :</b>\n"
                f"<pre>{snippet}</pre>"
            )
            await self.telegram.send_message(text, chat_id=chat_id)

        except Exception as e:
            await self.telegram.send_message(f"❌ Erreur lors de la lecture des logs : {e}", chat_id=chat_id)

    async def _cmd_restart(self, args: List[str], chat_id: str):
        if not args:
            await self.telegram.send_message("⚠️ Précisez le conteneur à redémarrer : <code>/restart &lt;nom_conteneur&gt;</code>", chat_id=chat_id)
            return

        target = args[0]
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Confirmer le Redémarrage", "callback_data": f"restart_exec:{target}"},
                    {"text": "❌ Annuler", "callback_data": "cancel_action"},
                ]
            ]
        }
        await self.telegram.send_message(
            f"⚠️ <b>Confirmation de Redémarrage</b>\n\nVoulez-vous vraiment redémarrer le conteneur <code>{TelegramNotifier.escape_html(target)}</code> ?",
            reply_markup=reply_markup,
            chat_id=chat_id,
        )

    async def _cmd_digest(self, chat_id: str):
        from src.notifiers.dispatcher import dispatcher
        stats = metrics_aggregator.get_stats_grouped_by_server()
        await dispatcher.send_periodic_digest(stats, period_hours=3)
        await self.telegram.send_message("✅ Rapport consolidé généré et envoyé !", chat_id=chat_id)

    async def _cmd_ai(self, args: List[str], chat_id: str):
        if not args:
            await self.telegram.send_message("⚠️ Précisez le conteneur : <code>/ai &lt;nom_conteneur&gt;</code>", chat_id=chat_id)
            return

        target = args[0]
        await self._perform_ai_diagnosis(target, chat_id)

    # ── Callbacks des Boutons Interactifs ───────────────────────────────────────

    async def _handle_callback_query(
        self,
        cb_id: str,
        data: str,
        chat_id: str,
        message_id: int,
        orig_text: str,
        sender: str,
    ):
        parts = data.split(":")
        action = parts[0]

        # 1. Navigation Menus
        if action == "cmd":
            subcmd = parts[1]
            await self.telegram.answer_callback_query(cb_id, text=f"Chargement {subcmd}...")
            if subcmd == "status":
                await self._cmd_status(chat_id)
            elif subcmd == "servers":
                await self._cmd_servers(chat_id)
            elif subcmd == "mutes":
                await self._cmd_mutes_list(chat_id)
            elif subcmd == "digest":
                await self._cmd_digest(chat_id)

        # 2. Bouton Muter
        elif action == "mute":
            pattern = parts[1]
            duration_min = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 120
            mutes_manager.mute(pattern, duration_min, reason=f"Bouton Telegram cliqué par @{sender}")
            await self.telegram.answer_callback_query(
                cb_id,
                text=f"🔇 '{pattern}' mis en sourdine pour {duration_min // 60}h !",
                show_alert=True,
            )
            # Met à jour le message pour afficher la confirmation
            new_text = orig_text + f"\n\n🔇 <i>Mis en sourdine pour {duration_min // 60}h par @{sender}</i>"
            await self.telegram.edit_message_text(chat_id, message_id, new_text, reply_markup=None)

        # 3. Bouton Voir Logs
        elif action == "logs":
            target = parts[1]
            await self.telegram.answer_callback_query(cb_id, text="Extraction des logs récents...")
            await self._cmd_logs([target, "25"], chat_id)

        # 4. Bouton Diagnostic IA
        elif action == "ai_rca":
            target = parts[1]
            await self.telegram.answer_callback_query(cb_id, text="🧠 Analyse IA en cours...")
            await self._perform_ai_diagnosis(target, chat_id, message_id)

        # 5. Bouton Redémarrer (Demande)
        elif action == "restart_ask":
            target = parts[1]
            await self.telegram.answer_callback_query(cb_id)
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Confirmer Redémarrage", "callback_data": f"restart_exec:{target}"},
                        {"text": "❌ Annuler", "callback_data": "cancel_action"},
                    ]
                ]
            }
            await self.telegram.edit_message_text(
                chat_id,
                message_id,
                orig_text + f"\n\n⚠️ <i>Confirmation requise pour redémarrer {target}</i>",
                reply_markup=reply_markup,
            )

        # 6. Bouton Redémarrer (Exécution)
        elif action == "restart_exec":
            target = parts[1]
            await self.telegram.answer_callback_query(cb_id, text="Redémarrage du conteneur en cours...")
            success = await self._restart_container(target)
            if success:
                res_text = f"✅ Conteneur <code>{TelegramNotifier.escape_html(target)}</code> redémarré avec succès par @{sender} !"
            else:
                res_text = f"❌ Impossible de redémarrer <code>{TelegramNotifier.escape_html(target)}</code>."
            await self.telegram.edit_message_text(chat_id, message_id, orig_text + f"\n\n{res_text}", reply_markup=None)

        # 7. Annuler action
        elif action == "cancel_action":
            await self.telegram.answer_callback_query(cb_id, text="Action annulée.")
            await self.telegram.edit_message_text(chat_id, message_id, orig_text + "\n\n<i>(Action annulée)</i>", reply_markup=None)

    async def _perform_ai_diagnosis(self, target: str, chat_id: str, message_id: Optional[int] = None):
        """Exécute et diffuse un diagnostic IA complet."""
        # Récupération des logs ou exceptions du conteneur
        details = ""
        loop = asyncio.get_running_loop()
        if docker_collector.client:
            try:
                containers = await loop.run_in_executor(None, docker_collector.client.containers.list, True)
                matching = [c for c in containers if target.lower() in c.name.lower()]
                if matching:
                    raw = await loop.run_in_executor(None, lambda: matching[0].logs(tail=40).decode("utf-8", errors="replace"))
                    details = raw
            except Exception:
                pass

        diagnosis = await ai_analyzer.analyze_incident(
            container_name=target,
            reason="Analyse à la demande",
            details=details,
            server_name=settings.server_name,
        )

        source = diagnosis.get("source", "Sentinel AI")
        formatted = diagnosis.get("formatted_text", "")

        text = (
            f"🧠 <b>[DIAGNOSTIC INTELLIGENT PAR {source.upper()}]</b> 🧠\n"
            f"📦 <b>Cible :</b> <code>{TelegramNotifier.escape_html(target)}</code>\n\n"
            f"{formatted}"
        )
        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": f"🔇 Muter {target} (2h)", "callback_data": f"mute:{target}:120"},
                    {"text": "📋 Voir Logs", "callback_data": f"logs:{target}"},
                ]
            ]
        }
        await self.telegram.send_message(text, reply_markup=reply_markup, chat_id=chat_id)

    async def _restart_container(self, target: str) -> bool:
        """Redémarre le conteneur via Docker."""
        if not docker_collector.client:
            return False
        loop = asyncio.get_running_loop()
        try:
            containers = await loop.run_in_executor(None, docker_collector.client.containers.list, True)
            matching = [c for c in containers if target.lower() in c.name.lower()]
            if not matching:
                return False
            c = matching[0]
            await loop.run_in_executor(None, c.restart)
            return True
        except Exception as e:
            logger.error(f"[TelegramBot] Échec restart conteneur {target} : {e}")
            return False

    @staticmethod
    def _parse_duration(duration_str: str) -> Optional[int]:
        """Convertit une durée comme '2h', '30m', '1d' en minutes."""
        match = re.match(r"^(\d+)([mhd]?)$", duration_str.strip().lower())
        if not match:
            return None
        val, unit = int(match.group(1)), match.group(2)
        if unit == "h":
            return val * 60
        elif unit == "d":
            return val * 1440
        return val


telegram_bot_handler = TelegramBotHandler()
