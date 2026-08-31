"""API Router for Webhooks, Health, Container Status, Direct Log Ingestion, and Notification Tests."""

import logging
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.config import settings
from src.notifiers.dispatcher import dispatcher
from src.analyzers.metrics_aggregator import metrics_aggregator
from src.analyzers.log_parser import LogParser
from src.scheduler.digest_job import digest_scheduler

logger = logging.getLogger(__name__)

router = APIRouter()


class LogIngestRequest(BaseModel):
    container_name: str = Field(..., description="Nom du conteneur ou service émetteur")
    line: Optional[str] = Field(None, description="Ligne unique de log")
    lines: Optional[List[str]] = Field(None, description="Liste de lignes de logs")
    payload: Optional[Dict[str, Any]] = Field(None, description="Objet JSON brut pour les logs structurés")


def _verify_secret_key(secret: Optional[str]):
    if not settings.debug and secret != settings.secret_key:
        raise HTTPException(status_code=403, detail="Clé secrète invalide ou manquante")


@router.get("/health")
async def health_check():
    """Health check endpoint pour vérifier l'état du microservice."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "version": "1.0.0",
    }


@router.get("/stats")
async def get_live_stats():
    """Retourne les métriques de trafic et de performance courantes en JSON."""
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
            "avg_cpu_percent": s.avg_cpu_percent,
            "max_memory_percent": s.max_memory_percent,
            "max_memory_mb": s.max_memory_mb,
            "docker_status": s.docker_status,
            "health_status": s.health_status,
        }
    return {"monitored_containers": len(result), "stats": result}


@router.get("/containers")
async def get_containers_overview():
    """Retourne la liste synthétique des conteneurs surveillés et leur état de santé."""
    stats = metrics_aggregator.get_all_stats()
    overview = []
    for name, s in stats.items():
        overview.append({
            "container_name": name,
            "status": s.docker_status,
            "health": s.health_status,
            "total_requests": s.total_requests,
            "error_rate_percent": s.error_5xx_rate_percent,
            "avg_cpu_percent": s.avg_cpu_percent,
            "max_memory_percent": s.max_memory_percent,
            "max_memory_mb": s.max_memory_mb,
            "critical_exceptions": len(s.critical_exceptions),
            "last_seen": s.last_seen.isoformat(),
        })
    return {"total": len(overview), "containers": overview}


@router.post("/digest/trigger")
async def trigger_manual_digest(secret: Optional[str] = Header(None, alias="X-Secret-Key")):
    """Déclenche manuellement l'envoi d'un digest consolidé sur les canaux actifs."""
    _verify_secret_key(secret)
    await digest_scheduler.execute_digest()
    return {"status": "success", "message": "Digest généré et expédié avec succès"}


@router.post("/notifications/test")
async def test_notifications(
    channel: str = Query("all", description="Canal à tester : telegram, discord, whatsapp, email, ou all"),
    secret: Optional[str] = Header(None, alias="X-Secret-Key"),
):
    """Envoie un message de test sur le ou les canaux spécifiés."""
    _verify_secret_key(secret)
    valid_channels = ("telegram", "discord", "whatsapp", "email", "all")
    if channel.lower() not in valid_channels:
        raise HTTPException(
            status_code=400,
            detail=f"Canal invalide '{channel}'. Choix possibles : {', '.join(valid_channels)}",
        )

    results = await dispatcher.test_notifications(channel=channel.lower())
    return {
        "status": "success",
        "tested_channel": channel,
        "results": results,
    }


@router.post("/logs/ingest")
async def ingest_logs(
    payload: LogIngestRequest,
    secret: Optional[str] = Header(None, alias="X-Secret-Key"),
):
    """
    Ingestion directe de logs applicatifs par HTTP.
    Permet à une application tierce d'envoyer ses logs directement à DokploySentinel.
    """
    _verify_secret_key(secret)
    container_name = payload.container_name

    raw_lines: List[str] = []
    if payload.line:
        raw_lines.append(payload.line)
    if payload.lines:
        raw_lines.extend(payload.lines)
    if payload.payload:
        import json
        raw_lines.append(json.dumps(payload.payload))

    if not raw_lines:
        raise HTTPException(status_code=400, detail="Aucun contenu de log fourni")

    processed_count = 0
    errors_detected = 0

    for line in raw_lines:
        entry = LogParser.parse_line(line, container_name)
        metrics_aggregator.record(entry, latency_threshold_ms=settings.latency_alert_threshold_ms)
        processed_count += 1

        if entry.is_critical_exception:
            errors_detected += 1
            await dispatcher.send_critical_alert(
                container_name=container_name,
                reason="❌ Exception critique reçue via Ingestion de Logs HTTP",
                details=entry.raw_line,
            )

    return {
        "status": "success",
        "container_name": container_name,
        "processed_lines": processed_count,
        "errors_detected": errors_detected,
    }


@router.post("/webhooks/dokploy")
async def dokploy_webhook(request: Request):
    """
    Réception des webhooks Dokploy (déploiements, arrêts, alertes de build).
    """
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    event_type = payload.get("event") or payload.get("type") or "Dokploy Event"
    title = payload.get("title") or payload.get("name") or "Application Dokploy"
    description = payload.get("description") or payload.get("message") or str(payload)

    logger.info(f"[Dokploy Webhook] Événement reçu : {event_type} — {title}")

    # Relayer l'alerte sur Telegram / Discord / WhatsApp / Email si anomalie
    if any(keyword in str(payload).lower() for keyword in ["fail", "error", "crash", "stop", "unhealthy", "oom"]):
        await dispatcher.send_critical_alert(
            container_name=title,
            reason=f"⚠️ Notification Webhook Dokploy : {event_type}",
            details=description,
        )

    return {"status": "received", "event": event_type}
