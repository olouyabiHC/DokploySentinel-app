"""Scheduler for periodic health digests and remote server heartbeat monitoring."""

import logging
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config import settings
from src.analyzers.metrics_aggregator import metrics_aggregator
from src.notifiers.dispatcher import dispatcher

logger = logging.getLogger(__name__)


class DigestScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    async def execute_digest(self):
        """Exécute la génération et l'envoi du rapport consolidé multi-serveurs."""
        logger.info("[DigestScheduler] Déclenchement du rapport périodique...")
        stats_grouped = metrics_aggregator.get_stats_grouped_by_server()
        await dispatcher.send_periodic_digest(stats_grouped, period_hours=settings.digest_interval_hours)
        metrics_aggregator.reset_stats()

    async def check_server_heartbeats(self):
        """Vérifie si des serveurs VPS distants n'ont plus donné de signe de vie."""
        now = datetime.now(timezone.utc)
        for srv in metrics_aggregator._servers.values():
            if srv.server_name == settings.server_name:
                continue  # Le serveur local est toujours actif

            elapsed = (now - srv.last_heartbeat).total_seconds()
            if elapsed > settings.agent_heartbeat_timeout_seconds and not srv.alerted_offline:
                srv.status = "offline"
                srv.alerted_offline = True
                logger.warning(f"[Heartbeat] Perte de signal pour le serveur VPS : {srv.server_name}")
                await dispatcher.send_server_offline_alert(srv.server_name, int(elapsed))

    def start(self):
        # 1. Job de Digest périodique
        trigger_digest = IntervalTrigger(hours=settings.digest_interval_hours)
        self.scheduler.add_job(
            self.execute_digest,
            trigger=trigger_digest,
            id="periodic_health_digest",
            name=f"Rapport de santé toutes les {settings.digest_interval_hours}h",
            replace_existing=True,
        )

        # 2. Job de surveillance des battements de cœur (Heartbeat)
        trigger_heartbeat = IntervalTrigger(seconds=60)
        self.scheduler.add_job(
            self.check_server_heartbeats,
            trigger=trigger_heartbeat,
            id="server_heartbeat_monitor",
            name="Surveillance des Heartbeats Serveurs",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info(f"[DigestScheduler] Planifié toutes les {settings.digest_interval_hours} heures.")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("[DigestScheduler] Arrêté.")


digest_scheduler = DigestScheduler()
