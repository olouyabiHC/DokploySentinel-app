"""Scheduler for periodic health digests."""

import logging
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
        """Exécute la génération et l'envoi du rapport consolidé."""
        logger.info("[DigestScheduler] Déclenchement du rapport périodique...")
        stats = metrics_aggregator.get_all_stats()
        await dispatcher.send_periodic_digest(stats, period_hours=settings.digest_interval_hours)
        metrics_aggregator.reset_stats()

    def start(self):
        trigger = IntervalTrigger(hours=settings.digest_interval_hours)
        self.scheduler.add_job(
            self.execute_digest,
            trigger=trigger,
            id="periodic_health_digest",
            name=f"Rapport de santé toutes les {settings.digest_interval_hours}h",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(f"[DigestScheduler] Planifié toutes les {settings.digest_interval_hours} heures.")

    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("[DigestScheduler] Arrêté.")


digest_scheduler = DigestScheduler()
