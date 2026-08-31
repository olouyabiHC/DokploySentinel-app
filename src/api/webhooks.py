"""API Router for Webhooks, Health, and Manual Digest Triggers."""

import logging
from fastapi import APIRouter, Header, HTTPException, Request
from typing import Dict, Any

from src.config import settings
from src.notifiers.dispatcher import dispatcher
from src.analyzers.metrics_aggregator import metrics_aggregator
from src.scheduler.digest_job import digest_scheduler

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@router.get("/stats")
async def get_live_stats():
    """Retourne les métriques courantes en JSON."""
    stats = metrics_aggregator.get_all_stats()
    result = {}
    for name, s in stats.items():
        result[name] = {
            "total_requests": s.total_requests,
            "2xx": s.count_2xx,
            "4xx": s.count_4xx,
            "5xx": s.count_5xx,
            "error_rate_5xx_percent": s.error_5xx_rate_percent,
            "median_latency_ms": s.median_latency_ms,
            "p95_latency_ms": s.p95_latency_ms,
            "slow_requests_count": len(s.slow_requests),
            "critical_exceptions_count": len(s.critical_exceptions),
        }
    return {"monitored_containers": len(result), "stats": result}


@router.post("/digest/trigger")
async def trigger_manual_digest(secret: str = Header(None, alias="X-Secret-Key")):
    """Déclenche manuellement l'envoi d'un digest (utile pour tester sans attendre 3h)."""
    if secret != settings.secret_key and not settings.debug:
        raise HTTPException(status_code=403, detail="Invalid Secret Key")

    await digest_scheduler.execute_digest()
    return {"status": "success", "message": "Digest envoyé avec succès"}


@router.post("/webhooks/dokploy")
async def dokploy_webhook(request: Request):
    """
    Réception des webhooks Dokploy (notifications de déploiement, redémarrage, etc.).
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    event_type = payload.get("event") or payload.get("type") or "Dokploy Event"
    title = payload.get("title") or payload.get("name") or "Application Dokploy"
    description = payload.get("description") or payload.get("message") or str(payload)

    logger.info(f"[Dokploy Webhook] Événement reçu : {event_type} — {title}")

    # Relayer l'alerte sur Telegram / Discord si c'est un échec ou avertissement
    if any(keyword in str(payload).lower() for keyword in ["fail", "error", "crash", "stop", "unhealthy"]):
        await dispatcher.send_critical_alert(
            container_name=title,
            reason=f"⚠️ Notification Webhook Dokploy : {event_type}",
            details=description
        )

    return {"status": "received", "event": event_type}
