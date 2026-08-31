"""Main FastAPI application for DokploySentinel 2.0 Hub."""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.config import settings
from src.api.webhooks import router as api_router
from src.collectors.docker_collector import docker_collector
from src.collectors.uptime_prober import uptime_prober
from src.scheduler.digest_job import digest_scheduler
from src.services.telegram_bot_handler import telegram_bot_handler

# Configuration des logs
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("DokploySentinel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Démarrage de {settings.app_name} Hub 2.0 sur [{settings.server_name}] ({settings.app_env})...")

    # 1. Démarrer le collecteur Docker local (thread non-bloquant)
    await docker_collector.start()

    # 2. Démarrer les sondes Uptime / SSL
    uptime_prober.start()

    # 3. Démarrer le planificateur de digest et surveillance de heartbeat
    digest_scheduler.start()

    # 4. Enregistrement automatique du Webhook Telegram si configuré
    if settings.telegram_enabled and settings.telegram_bot_token:
        webhook_target = settings.telegram_webhook_url or "https://sentinel.lekyn.com/api/v1/telegram/webhook"
        try:
            # Lancement asynchrone non-bloquant de la configuration webhook
            asyncio.create_task(
                telegram_bot_handler.telegram.set_webhook(
                    webhook_url=webhook_target,
                    secret_token=settings.telegram_webhook_secret,
                )
            )
        except Exception as e:
            logger.debug(f"[Lifespan] Erreur configuration automatique webhook Telegram : {e}")

    yield

    logger.info(f"Arrêt de {settings.app_name}...")
    await docker_collector.stop()
    uptime_prober.stop()
    digest_scheduler.stop()


app = FastAPI(
    title=settings.app_name,
    description="Hub d'observabilité centralisé 2.0, Bot Telegram interactif, surveillance multi-VPS et digest IA pour serveurs Dokploy",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "version": "2.0.0",
        "role": "Hub Central & Bot Interactif",
        "server_name": settings.server_name,
        "status": "running",
        "digest_interval_hours": settings.digest_interval_hours,
        "docs": "/docs",
    }
