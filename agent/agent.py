"""Sentinel-Agent: Micro-agent autonome et ultra-léger pour VPS distants Dokploy."""

import asyncio
import logging
import os
import shutil
import threading
import docker
import httpx

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Sentinel-Agent] %(message)s",
)
logger = logging.getLogger("SentinelAgent")

# Paramètres d'environnement
HUB_URL = os.getenv("SENTINEL_HUB_URL", "https://sentinel.lekyn.com").rstrip("/")
API_KEY = os.getenv("SENTINEL_API_KEY", "")
SERVER_NAME = os.getenv("SERVER_NAME", "VPS-Distant")
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET_PATH", "unix://var/run/docker.sock")
SYNC_INTERVAL = int(os.getenv("SYNC_INTERVAL_SECONDS", "20"))
IGNORED_PATTERNS = [
    p.strip().lower()
    for p in os.getenv(
        "IGNORED_CONTAINER_PATTERNS",
        "pgbouncer,postgres,redis,dokploy-traefik,dokploy-sentinel,sentinel-agent",
    ).split(",")
    if p.strip()
]


class SentinelAgent:
    def __init__(self):
        self.docker_client = None
        self.running = False
        self._pending_logs = []
        self._pending_alerts = []
        self._event_thread = None

    def connect(self) -> bool:
        try:
            self.docker_client = docker.DockerClient(base_url=DOCKER_SOCKET)
            self.docker_client.ping()
            logger.info(f"Connecté au moteur Docker local sur le serveur [{SERVER_NAME}].")
            return True
        except Exception as e:
            logger.error(f"Impossible de se connecter au socket Docker ({DOCKER_SOCKET}) : {e}")
            return False

    def should_monitor(self, name: str) -> bool:
        name_lower = name.lower()
        return not any(ign in name_lower for ign in IGNORED_PATTERNS)

    def get_host_metrics(self) -> tuple[float, float, float]:
        """Mesure l'utilisation globale du VPS (RAM et Disque)."""
        host_cpu = 0.0
        host_mem = 0.0
        host_disk = 0.0

        # Disque
        try:
            total, used, free = shutil.disk_usage("/")
            host_disk = round((used / total) * 100.0, 1)
        except Exception:
            pass

        # Mémoire RAM (lecture depuis /proc/meminfo sous Linux)
        try:
            if os.path.exists("/proc/meminfo"):
                meminfo = {}
                with open("/proc/meminfo", "r") as f:
                    for line in f:
                        parts = line.split(":")
                        if len(parts) == 2:
                            meminfo[parts[0].strip()] = int(parts[1].strip().split()[0])
                total_k = meminfo.get("MemTotal", 1)
                avail_k = meminfo.get("MemAvailable", 0)
                used_k = total_k - avail_k
                host_mem = round((used_k / total_k) * 100.0, 1)
        except Exception:
            pass

        return host_cpu, host_mem, host_disk

    async def start(self):
        self.running = True
        while not self.connect() and self.running:
            logger.warning("Nouvelle tentative de connexion Docker dans 5s...")
            await asyncio.sleep(5)

        logger.info(f"🛰️ Démarrage de l'agent sur [{SERVER_NAME}] ➔ Hub: {HUB_URL}")

        loop = asyncio.get_running_loop()

        # 1. Écoute continue des événements Docker dans un thread dédié
        self._event_thread = threading.Thread(
            target=self._listen_events_thread,
            args=(loop,),
            daemon=True,
            name="AgentEventsThread",
        )
        self._event_thread.start()

        # 2. Boucle périodique de collecte et synchronisation
        asyncio.create_task(self._sync_loop())

    def _listen_events_thread(self, loop: asyncio.AbstractEventLoop):
        """Capte instantanément tout crash, arrêt anormal ou OOM sans bloquer asyncio."""
        while self.running:
            try:
                for event in self.docker_client.events(decode=True, filters={"type": "container"}):
                    if not self.running:
                        break
                    action = event.get("Action", "")
                    actor = event.get("Actor", {})
                    attributes = actor.get("Attributes", {})
                    c_name = attributes.get("name", "unknown")

                    if not self.should_monitor(c_name):
                        continue

                    # Détection OOMKilled
                    if action == "oom":
                        alert = {
                            "container_name": c_name,
                            "reason": "💥 Out Of Memory (OOMKilled) — Limite RAM dépassée !",
                            "details": str(attributes),
                        }
                        self._pending_alerts.append(alert)
                        logger.warning(f"Alerte immédiate OOM détectée sur {c_name}")
                        asyncio.run_coroutine_threadsafe(self._send_sync_payload(), loop)

                    # Détection crash / die anormal
                    elif action == "die":
                        exit_code = attributes.get("exitCode")
                        if exit_code and exit_code != "0":
                            alert = {
                                "container_name": c_name,
                                "reason": f"🛑 Arrêt anormal / Crash du conteneur (Exit Code: {exit_code})",
                                "details": f"Événement: {action} | Image: {attributes.get('image', 'N/A')}",
                            }
                            self._pending_alerts.append(alert)
                            logger.warning(f"Alerte immédiate Crash détectée sur {c_name} (Code {exit_code})")
                            asyncio.run_coroutine_threadsafe(self._send_sync_payload(), loop)

                    # Détection healthcheck unhealthy
                    elif "health_status" in action and "unhealthy" in action:
                        alert = {
                            "container_name": c_name,
                            "reason": "🩺 Échec des Healthchecks Docker (Statut Unhealthy)",
                            "details": f"Événement: {action}",
                        }
                        self._pending_alerts.append(alert)
                        logger.warning(f"Alerte immédiate Unhealthy détectée sur {c_name}")
                        asyncio.run_coroutine_threadsafe(self._send_sync_payload(), loop)

            except Exception as e:
                if self.running:
                    import time
                    time.sleep(3)

    async def _sync_loop(self):
        """Scanne les conteneurs et envoie le rapport consolidé au Hub toutes les N secondes."""
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                containers_data = []
                containers = await loop.run_in_executor(None, self.docker_client.containers.list)

                for container in containers:
                    if not self.should_monitor(container.name):
                        continue

                    # 1. Logs récents
                    raw_logs = await loop.run_in_executor(
                        None,
                        lambda c=container: c.logs(since=SYNC_INTERVAL + 5, timestamps=False).decode(
                            "utf-8", errors="replace"
                        ),
                    )
                    for line in raw_logs.splitlines():
                        if line.strip():
                            self._pending_logs.append(f"[{container.name}] {line}")

                    # 2. Stats ressources
                    c_attrs = container.attrs or {}
                    c_state = c_attrs.get("State", {})
                    status = c_state.get("Status", "running")
                    health_status = c_state.get("Health", {}).get(
                        "Status", "healthy" if status == "running" else "unknown"
                    )

                    stats = await loop.run_in_executor(None, lambda c=container: c.stats(stream=False))
                    cpu_p, mem_p, mem_mb = self._calc_usage(stats)

                    containers_data.append({
                        "container_name": container.name,
                        "cpu_percent": cpu_p,
                        "memory_percent": mem_p,
                        "memory_mb": mem_mb,
                        "status": status,
                        "health": health_status,
                    })

                # Transmettre au Hub central
                await self._send_sync_payload(containers_data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur boucle de synchronisation : {e}")

            await asyncio.sleep(SYNC_INTERVAL)

    async def _send_sync_payload(self, containers_data=None):
        """Envoie les métriques, logs et alertes au Hub avec file d'attente de secours."""
        host_cpu, host_mem, host_disk = self.get_host_metrics()

        payload = {
            "server_name": SERVER_NAME,
            "host_cpu_percent": host_cpu,
            "host_memory_percent": host_mem,
            "host_disk_percent": host_disk,
            "containers": containers_data or [],
            "logs": self._pending_logs[:100],  # Max 100 logs par paquet
            "alerts": list(self._pending_alerts),
        }

        headers = {
            "Content-Type": "application/json",
            "X-Secret-Key": API_KEY,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(f"{HUB_URL}/api/v1/agent/sync", json=payload, headers=headers)
                if resp.status_code == 200:
                    # Succès : vider les éléments envoyés
                    self._pending_logs = self._pending_logs[100:]
                    self._pending_alerts.clear()
                    logger.debug(f"Sync réussie vers {HUB_URL}")
                else:
                    logger.warning(f"Échec sync HTTP {resp.status_code} : {resp.text}")
        except Exception as e:
            logger.warning(f"Erreur réseau lors de la synchronisation vers {HUB_URL} (mise en buffer) : {e}")

    @staticmethod
    def _calc_usage(stats: dict) -> tuple[float, float, float]:
        try:
            mem_stats = stats.get("memory_stats", {})
            mem_usage = mem_stats.get("usage", 0)
            mem_limit = mem_stats.get("limit", 1)
            mem_mb = round(mem_usage / (1024 * 1024), 1)
            mem_p = round((mem_usage / mem_limit) * 100.0, 1) if mem_limit > 0 else 0.0

            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            cpu_delta = (
                cpu_stats.get("cpu_usage", {}).get("total_usage", 0)
                - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            )
            sys_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)
            online_cpus = cpu_stats.get("online_cpus", len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", []) or [1]))

            cpu_p = 0.0
            if sys_delta > 0 and cpu_delta > 0:
                cpu_p = round((cpu_delta / sys_delta) * online_cpus * 100.0, 1)

            return cpu_p, mem_p, mem_mb
        except Exception:
            return 0.0, 0.0, 0.0


if __name__ == "__main__":
    agent = SentinelAgent()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(agent.start())
        loop.run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Arrêt de l'agent.")
