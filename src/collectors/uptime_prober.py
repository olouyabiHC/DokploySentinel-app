"""Uptime and SSL certificate health prober for external websites and client platforms."""

import asyncio
import logging
import socket
import ssl
from datetime import datetime, timezone
from typing import Dict, List, Optional
import httpx

from src.config import settings
from src.notifiers.dispatcher import dispatcher

logger = logging.getLogger(__name__)


class TargetHealth:
    def __init__(self, url: str):
        self.url = url
        self.status: str = "unknown"  # "UP", "DOWN", "DEGRADED"
        self.http_code: Optional[int] = None
        self.latency_ms: Optional[float] = None
        self.last_checked: Optional[datetime] = None
        self.consecutive_failures: int = 0
        self.ssl_days_left: Optional[int] = None
        self.last_error: Optional[str] = None


class UptimeProber:
    def __init__(self):
        self.targets: Dict[str, TargetHealth] = {}
        self.running: bool = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        targets = settings.http_targets_list
        if not targets:
            logger.info("[UptimeProber] Aucune cible HTTP configurée dans MONITORED_HTTP_TARGETS.")
            return

        for url in targets:
            self.targets[url] = TargetHealth(url)

        self.running = True
        self._task = asyncio.create_task(self._probe_loop())
        logger.info(f"[UptimeProber] Démarré pour {len(targets)} cibles HTTP.")

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("[UptimeProber] Arrêté.")

    async def _probe_loop(self):
        while self.running:
            try:
                tasks = [self.probe_target(url) for url in list(self.targets.keys())]
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[UptimeProber] Erreur dans la boucle de sonde : {e}")

            await asyncio.sleep(settings.uptime_probe_interval_seconds)

    async def probe_target(self, url: str):
        target = self.targets.get(url)
        if not target:
            target = TargetHealth(url)
            self.targets[url] = target

        start_time = asyncio.get_event_loop().time()
        target.last_checked = datetime.now(timezone.utc)

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url)
                latency = round((asyncio.get_event_loop().time() - start_time) * 1000.0, 1)
                target.http_code = resp.status_code
                target.latency_ms = latency

                if resp.status_code < 400:
                    target.status = "UP"
                    target.consecutive_failures = 0
                    target.last_error = None
                else:
                    target.status = "DOWN"
                    target.consecutive_failures += 1
                    target.last_error = f"HTTP {resp.status_code}"
                    await dispatcher.send_uptime_alert(
                        target_url=url,
                        reason=f"🛑 Statut HTTP anormal : {resp.status_code}",
                        details=f"Code: {resp.status_code} | Latence: {latency}ms",
                    )

        except Exception as e:
            target.status = "DOWN"
            target.consecutive_failures += 1
            target.last_error = str(e)
            target.http_code = None
            target.latency_ms = None

            await dispatcher.send_uptime_alert(
                target_url=url,
                reason="💥 Site ou API inaccessible (Erreur de connexion / Timeout)",
                details=str(e),
            )

        # Vérification expiration SSL si HTTPS
        if url.startswith("https://"):
            ssl_days = await asyncio.to_thread(self._check_ssl_expiry, url)
            target.ssl_days_left = ssl_days
            if ssl_days is not None and ssl_days <= 7:
                await dispatcher.send_uptime_alert(
                    target_url=url,
                    reason=f"🔒 Certificat SSL expire dans {ssl_days} jour(s) !",
                    details=f"Renouvellement Let's Encrypt / SSL requis d'urgence pour {url}.",
                )

    @staticmethod
    def _check_ssl_expiry(url: str) -> Optional[int]:
        """Vérifie le nombre de jours restants avant expiration du certificat SSL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname
            port = parsed.port or 443

            ctx = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=5.0) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    not_after_str = cert.get("notAfter")
                    if not_after_str:
                        not_after = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                        days = (not_after - datetime.now(timezone.utc)).days
                        return max(0, days)
        except Exception:
            return None
        return None

    def get_overview(self) -> List[Dict]:
        overview = []
        for url, t in self.targets.items():
            overview.append({
                "url": url,
                "status": t.status,
                "http_code": t.http_code,
                "latency_ms": t.latency_ms,
                "last_checked": t.last_checked.isoformat() if t.last_checked else None,
                "ssl_days_left": t.ssl_days_left,
                "last_error": t.last_error,
            })
        return overview


uptime_prober = UptimeProber()
