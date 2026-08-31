"""Main FastAPI application for DokploySentinel Hub."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.config import settings
from src.api.webhooks import router as api_router
from src.collectors.docker_collector import docker_collector
from src.collectors.uptime_prober import uptime_prober
from src.scheduler.digest_job import digest_scheduler

# Configuration des logs
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("DokploySentinel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Démarrage de {settings.app_name} Hub sur [{settings.server_name}] ({settings.app_env})...")

    # 1. Démarrer le collecteur Docker local
    await docker_collector.start()

    # 2. Démarrer les sondes Uptime / SSL
    uptime_prober.start()

    # 3. Démarrer le planificateur de digest et surveillance de heartbeat
    digest_scheduler.start()

    yield

    logger.info(f"Arrêt de {settings.app_name}...")
    await docker_collector.stop()
    uptime_prober.stop()
    digest_scheduler.stop()


app = FastAPI(
    title=settings.app_name,
    description="Hub d'observabilité centralisé, surveillance multi-VPS et digest de santé pour serveurs Dokploy",
    version="1.1.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "version": "1.1.0",
        "role": "Hub Central",
        "server_name": settings.server_name,
        "status": "running",
        "digest_interval_hours": settings.digest_interval_hours,
        "docs": "/docs",
    }
