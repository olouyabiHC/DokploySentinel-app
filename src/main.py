"""Main FastAPI application for DokploySentinel."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.config import settings
from src.api.webhooks import router as api_router
from src.collectors.docker_collector import docker_collector
from src.scheduler.digest_job import digest_scheduler

# Configuration des logs
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("DokploySentinel")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Démarrage de {settings.app_name} ({settings.app_env})...")
    
    # 1. Démarrer le collecteur Docker
    await docker_collector.start()
    
    # 2. Démarrer le planificateur de digest périodique
    digest_scheduler.start()
    
    yield
    
    logger.info(f"Arrêt de {settings.app_name}...")
    await docker_collector.stop()
    digest_scheduler.stop()


app = FastAPI(
    title=settings.app_name,
    description="Plateforme de surveillance, observabilité et digest de santé pour applications Dokploy",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "app": settings.app_name,
        "version": "1.0.0",
        "status": "running",
        "digest_interval_hours": settings.digest_interval_hours,
        "docs": "/docs",
    }
