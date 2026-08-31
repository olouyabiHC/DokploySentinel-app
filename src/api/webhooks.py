"""API Router for Webhooks, Multi-Server Agent Sync, Interactive Telegram Bot, Mutes, and Uptime."""

import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.config import settings
from src.notifiers.dispatcher import dispatcher
from src.analyzers.metrics_aggregator import metrics_aggregator
from src.analyzers.log_parser import LogParser
from src.collectors.uptime_prober import uptime_prober
from src.scheduler.digest_job import digest_scheduler
from src.services.mutes_manager import mutes_manager
from src.services.telegram_bot_handler import telegram_bot_handler
from src.services.ai_analyzer import ai_analyzer

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Modèles de Données Pydantic ───────────────────────────────────────────────

class ContainerReport(BaseModel):
    container_name: str
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    status: str = "running"
    health: str = "healthy"


class InstantAlertReport(BaseModel):
    container_name: str
    reason: str
    details: str = ""


class AgentSyncPayload(BaseModel):
    server_name: str = Field(..., description="Nom du serveur VPS émetteur (ex: VPS-Client-A)")
    host_cpu_percent: float = 0.0
    host_memory_percent: float = 0.0
    host_disk_percent: float = 0.0
    containers: List[ContainerReport] = []
    logs: List[str] = []
    alerts: List[InstantAlertReport] = []


class AgentHeartbeatPayload(BaseModel):
    server_name: str
    host_cpu_percent: float = 0.0
    host_memory_percent: float = 0.0
    host_disk_percent: float = 0.0


class LogIngestRequest(BaseModel):
    container_name: str
    server_name: Optional[str] = None
    line: Optional[str] = None
    lines: Optional[List[str]] = None
    payload: Optional[Dict[str, Any]] = None


class MuteCreateRequest(BaseModel):
    pattern: str = Field(..., description="Nom de conteneur ou motif (ex: wordpress, celery)")
    duration_minutes: Optional[int] = Field(None, description="Durée en minutes (None = permanent)")
    reason: str = "Manuel via API"
    server_name: Optional[str] = None


class AIDiagnoseRequest(BaseModel):
    container_name: str = "test-app"
    reason: str = "Exception"
    details: str = ""
    server_name: Optional[str] = None


def _verify_secret_key(secret: Optional[str]):
    if not settings.debug and secret != settings.secret_key:
        raise HTTPException(status_code=403, detail="Clé secrète invalide ou manquante")


# ── Endpoints de Base & Santé ────────────────────────────────────────────────

@router.get("/health")
async def health_check():
    """Health check endpoint pour vérifier l'état du microservice Hub."""
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "server_name": settings.server_name,
        "version": "2.0.0",
    }


# ── Interactive Telegram Bot Webhook ────────────────────────────────────────

@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    secret_token: Optional[str] = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    """Réception des événements et commandes Telegram envoyés par le Webhook officiel Telegram."""
    # Vérification optionnelle du token de sécurité Telegram
    if settings.telegram_webhook_secret and secret_token:
        if secret_token != settings.telegram_webhook_secret and not settings.debug:
            raise HTTPException(status_code=403, detail="Token de sécurité Telegram invalide")

    try:
        update_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Corps de requête JSON invalide")

    # Traitement asynchrone par le gestionnaire Telegram interactif
    await telegram_bot_handler.process_update(update_data)
    return {"ok": True}


@router.post("/telegram/setup-webhook")
async def setup_telegram_webhook(
    webhook_url: Optional[str] = Query(None, description="URL publique du webhook (ex: https://sentinel.lekyn.com/api/v1/telegram/webhook)"),
    secret: Optional[str] = Header(None, alias="X-Secret-Key"),
):
    """Configure automatiquement le Webhook auprès de Telegram."""
    _verify_secret_key(secret)
    target_url = webhook_url or settings.telegram_webhook_url or "https://sentinel.lekyn.com/api/v1/telegram/webhook"
    success = await telegram_bot_handler.telegram.set_webhook(
        webhook_url=target_url,
        secret_token=settings.telegram_webhook_secret,
    )
    if success:
        return {"status": "success", "message": f"Webhook Telegram configuré avec succès sur {target_url}"}
    raise HTTPException(status_code=500, detail="Échec de configuration du Webhook auprès de Telegram")


# ── Gestionnaire Dynamique des Sourdines (Mutes) ────────────────────────────

@router.get("/mutes")
async def get_active_mutes():
    """Retourne la liste des conteneurs ou patterns actuellement en sourdine."""
    return {"active_mutes": mutes_manager.get_active_mutes()}


@router.post("/mutes")
async def create_mute_rule(
    payload: MuteCreateRequest,
    secret: Optional[str] = Header(None, alias="X-Secret-Key"),
):
    """Crée une nouvelle règle de sourdine pour filtrer les alertes."""
    _verify_secret_key(secret)
    rule = mutes_manager.mute(
        pattern=payload.pattern,
        duration_minutes=payload.duration_minutes,
        reason=payload.reason,
        server_name=payload.server_name,
    )
    return {"status": "success", "rule": rule.to_dict()}


@router.delete("/mutes/{pattern}")
async def delete_mute_rule(
    pattern: str,
    secret: Optional[str] = Header(None, alias="X-Secret-Key"),
):
    """Supprime une règle de sourdine active."""
    _verify_secret_key(secret)
    if mutes_manager.unmute(pattern):
        return {"status": "success", "message": f"Sourdine levée pour '{pattern}'"}
    raise HTTPException(status_code=404, detail=f"Aucune sourdine active trouvée pour '{pattern}'")


# ── Diagnostic IA à la demande ──────────────────────────────────────────────

@router.post("/ai/diagnose")
async def ai_diagnose_endpoint(
    payload: AIDiagnoseRequest,
    secret: Optional[str] = Header(None, alias="X-Secret-Key"),
):
    """Génère un diagnostic IA pour une erreur ou stacktrace donnée."""
    _verify_secret_key(secret)
    result = await ai_analyzer.analyze_incident(
        container_name=payload.container_name,
        reason=payload.reason,
        details=payload.details,
        server_name=payload.server_name or settings.server_name,
    )
    return {"status": "success", "diagnosis": result}


# ── Endpoints Multi-Serveurs & Synchronisation Agent ─────────────────────────

@router.post("/agent/sync")
async def agent_sync(
    payload: AgentSyncPayload,
    secret: Optional[str] = Header(None, alias="X-Secret-Key"),
):
    """
    Endpoint de synchronisation périodique pour les Sentinel-Agents distants.
    Ingère en lot : logs, métriques conteneurs, santé du VPS et alertes instantanées.
    """
    _verify_secret_key(secret)
    s_name = payload.server_name

    # 1. Enregistrer le battement de cœur et métriques hôte
    metrics_aggregator.record_server_heartbeat(
        server_name=s_name,
        host_cpu=payload.host_cpu_percent,
        host_memory=payload.host_memory_percent,
        host_disk=payload.host_disk_percent,
    )

    # 2. Enregistrer les ressources conteneurs
    for c in payload.containers:
        metrics_aggregator.record_container_resources(
            container_name=c.container_name,
            cpu_percent=c.cpu_percent,
            memory_percent=c.memory_percent,
            memory_mb=c.memory_mb,
            status=c.status,
            health=c.health,
            server_name=s_name,
        )

    # 3. Parser et enregistrer les logs
    for line in payload.logs:
        if not line.strip():
            continue
        entry = LogParser.parse_line(line, container_name="unknown")
        metrics_aggregator.record(entry, latency_threshold_ms=settings.latency_alert_threshold_ms, server_name=s_name)

        if entry.is_critical_exception:
            await dispatcher.send_critical_alert(
                container_name=entry.container_name,
                reason="❌ Exception critique détectée dans les logs distants",
                details=entry.raw_line,
                server_name=s_name,
            )

    # 4. Traiter les alertes instantanées envoyées par l'agent (Crash / OOM)
    for alert in payload.alerts:
        await dispatcher.send_critical_alert(
            container_name=alert.container_name,
            reason=alert.reason,
            details=alert.details,
            server_name=s_name,
        )

    return {
        "status": "success",
        "server_name": s_name,
        "processed_containers": len(payload.containers),
        "processed_logs": len(payload.logs),
        "processed_alerts": len(payload.alerts),
    }


@router.post("/agent/heartbeat")
async def agent_heartbeat(
    payload: AgentHeartbeatPayload,
    secret: Optional[str] = Header(None, alias="X-Secret-Key"),
):
    """Signal de vie léger envoyé par les Sentinel-Agents distants."""
    _verify_secret_key(secret)
    metrics_aggregator.record_server_heartbeat(
        server_name=payload.server_name,
        host_cpu=payload.host_cpu_percent,
        host_memory=payload.host_memory_percent,
        host_disk=payload.host_disk_percent,
    )
    return {"status": "ok", "server_name": payload.server_name}


@router.get("/servers")
async def get_servers_overview():
    """Retourne la liste de tous les serveurs VPS connectés et leur statut de santé."""
    return {"servers": metrics_aggregator.get_servers_overview()}


@router.get("/uptime")
async def get_uptime_overview():
    """Retourne l'état en direct de toutes les sondes HTTP et des certificats SSL."""
    return {"targets": uptime_prober.get_overview()}


# ── Endpoints Conteneurs & Stats ─────────────────────────────────────────────

@router.get("/stats")
async def get_live_stats(server: Optional[str] = Query(None, description="Filtrer par serveur VPS")):
    """Retourne les métriques courantes regroupées par serveur."""
    grouped = metrics_aggregator.get_stats_grouped_by_server()
    if server:
        grouped = {server: grouped.get(server, {})}

    formatted = {}
    for s_name, containers in grouped.items():
        formatted[s_name] = {}
        for c_name, s in containers.items():
            formatted[s_name][c_name] = {
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

    return {"servers_count": len(formatted), "stats": formatted}


@router.get("/containers")
async def get_containers_overview(server: Optional[str] = Query(None, description="Filtrer par serveur VPS")):
    """Retourne la liste de tous les conteneurs surveillés à travers tous les VPS."""
    stats = metrics_aggregator.get_all_stats()
    overview = []
    for (s_name, c_name), s in stats.items():
        if server and s_name != server:
            continue
        overview.append({
            "server_name": s_name,
            "container_name": c_name,
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
    """Déclenche manuellement l'envoi d'un digest consolidé multi-serveurs sur Telegram."""
    _verify_secret_key(secret)
    await digest_scheduler.execute_digest()
    return {"status": "success", "message": "Digest multi-serveurs généré et expédié"}


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
    """Ingestion directe de logs applicatifs par HTTP."""
    _verify_secret_key(secret)
    server_name = payload.server_name or settings.server_name
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
        raise HTTPException(status_code=400, detail="Aucun log fourni")

    for line in raw_lines:
        entry = LogParser.parse_line(line, container_name)
        metrics_aggregator.record(entry, latency_threshold_ms=settings.latency_alert_threshold_ms, server_name=server_name)

        if entry.is_critical_exception:
            await dispatcher.send_critical_alert(
                container_name=container_name,
                reason="❌ Exception critique reçue par Ingestion HTTP",
                details=entry.raw_line,
                server_name=server_name,
            )

    return {
        "status": "success",
        "server_name": server_name,
        "container_name": container_name,
        "processed_lines": len(raw_lines),
    }


@router.post("/webhooks/dokploy")
async def dokploy_webhook(
    request: Request,
    server: Optional[str] = Query(None, description="Nom du serveur Dokploy"),
):
    """Réception des webhooks de déploiement de n'importe quel Dokploy (local ou distant)."""
    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    event_type = payload.get("event") or payload.get("type") or "Dokploy Event"
    title = payload.get("title") or payload.get("name") or "Application Dokploy"
    description = payload.get("description") or payload.get("message") or str(payload)
    srv_name = server or settings.server_name

    logger.info(f"[Dokploy Webhook] [{srv_name}] Événement : {event_type} — {title}")

    if any(keyword in str(payload).lower() for keyword in ["fail", "error", "crash", "stop", "unhealthy", "oom"]):
        await dispatcher.send_critical_alert(
            container_name=title,
            reason=f"⚠️ Notification Webhook Dokploy : {event_type}",
            details=description,
            server_name=srv_name,
        )

    return {"status": "received", "server": srv_name, "event": event_type}
