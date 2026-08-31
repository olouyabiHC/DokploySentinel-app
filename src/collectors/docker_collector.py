"""Docker log, container lifecycle events, and resource metrics collector."""

import asyncio
import logging
from typing import Dict, Optional, Set
import docker

from src.config import settings
from src.analyzers.log_parser import LogParser
from src.analyzers.metrics_aggregator import metrics_aggregator
from src.notifiers.dispatcher import dispatcher

logger = logging.getLogger(__name__)


class DockerCollector:
    def __init__(self):
        self.client: Optional[docker.DockerClient] = None
        self.running = False
        self._active_tasks: Set[asyncio.Task] = set()
        self._last_log_timestamps: Dict[str, int] = {}

    def connect(self) -> bool:
        try:
            self.client = docker.DockerClient(base_url=settings.docker_socket_path)
            self.client.ping()
            logger.info("[DockerCollector] Connecté avec succès au démon Docker.")
            return True
        except Exception as e:
            logger.warning(
                f"[DockerCollector] Impossible de se connecter au socket Docker ({settings.docker_socket_path}) : {e}"
            )
            logger.info("[DockerCollector] Mode autonome actif (en attente de conteneurs ou webhooks).")
            return False

    def should_monitor_container(self, container_name: str) -> bool:
        name_lower = container_name.lower()

        # Ignorer les conteneurs dans la liste d'exclusion
        for ignored in settings.ignored_patterns_list:
            if ignored in name_lower:
                return False

        # Si liste de filtres définie, doit correspondre à au moins un motif
        if settings.monitored_patterns_list:
            return any(mon in name_lower for mon in settings.monitored_patterns_list)

        return True

    async def start(self):
        self.running = True
        if not self.connect():
            return

        # 1. Écoute des événements de cycle de vie (crash, restart, OOM, unhealthy)
        event_task = asyncio.create_task(self._listen_docker_events())
        self._active_tasks.add(event_task)

        # 2. Surveillance des logs en continu
        log_task = asyncio.create_task(self._monitor_containers_logs())
        self._active_tasks.add(log_task)

        # 3. Surveillance périodique de l'utilisation CPU / RAM
        stats_task = asyncio.create_task(self._monitor_containers_resources())
        self._active_tasks.add(stats_task)

    async def stop(self):
        self.running = False
        for task in self._active_tasks:
            task.cancel()
        self._active_tasks.clear()
        logger.info("[DockerCollector] Arrêté.")

    async def _listen_docker_events(self):
        """Surveille les événements Docker en temps réel (arrêt brutal, OOM, crash, unhealthy)."""
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                events = await loop.run_in_executor(
                    None,
                    lambda: self.client.events(decode=True, filters={"type": "container"}),
                )
                for event in events:
                    if not self.running:
                        break
                    action = event.get("Action", "")
                    actor = event.get("Actor", {})
                    attributes = actor.get("Attributes", {})
                    container_name = attributes.get("name", "unknown")

                    if not self.should_monitor_container(container_name):
                        continue

                    # Détection OOMKilled
                    if action == "oom":
                        await dispatcher.send_critical_alert(
                            container_name=container_name,
                            reason="💥 Out Of Memory (OOMKilled) — Dépassement critique de mémoire !",
                            details=str(attributes),
                        )
                    # Détection arrêt anormal (crash / die avec exit code != 0)
                    elif action == "die":
                        exit_code = attributes.get("exitCode")
                        if exit_code and exit_code != "0":
                            await dispatcher.send_critical_alert(
                                container_name=container_name,
                                reason=f"🛑 Arrêt anormal du conteneur (Exit Code: {exit_code})",
                                details=f"Événement: {action} | Image: {attributes.get('image', 'N/A')}",
                            )
                    # Détection conteneur devenu malsain (Healthcheck Docker KO)
                    elif "health_status" in action and "unhealthy" in action:
                        await dispatcher.send_critical_alert(
                            container_name=container_name,
                            reason="🩺 Conteneur passé à l'état Unhealthy (Échec du Healthcheck)",
                            details=f"Événement: {action}",
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DockerCollector] Erreur boucle événements Docker : {e}")
                await asyncio.sleep(5)

    async def _monitor_containers_logs(self):
        """Scanne périodiquement les logs récents de chaque conteneur actif."""
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                containers = await loop.run_in_executor(None, self.client.containers.list)
                for container in containers:
                    if not self.should_monitor_container(container.name):
                        continue

                    cid = container.id
                    # On lit les logs depuis les 30 dernières secondes
                    raw_logs = await loop.run_in_executor(
                        None,
                        lambda c=container: c.logs(since=30, timestamps=False).decode("utf-8", errors="replace"),
                    )

                    for line in raw_logs.splitlines():
                        if not line.strip():
                            continue
                        entry = LogParser.parse_line(line, container.name)
                        metrics_aggregator.record(entry, latency_threshold_ms=settings.latency_alert_threshold_ms)

                        # Alerte immédiate si exception critique rencontrée
                        if entry.is_critical_exception:
                            await dispatcher.send_critical_alert(
                                container_name=container.name,
                                reason="❌ Exception / Crash applicatif détecté dans les logs",
                                details=entry.raw_line,
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DockerCollector] Erreur scan des logs : {e}")

            await asyncio.sleep(30)

    async def _monitor_containers_resources(self):
        """Collecte les statistiques de mémoire et CPU des conteneurs actifs."""
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                containers = await loop.run_in_executor(None, self.client.containers.list)
                for container in containers:
                    if not self.should_monitor_container(container.name):
                        continue

                    # Récupérer l'état de santé
                    c_attrs = container.attrs or {}
                    c_state = c_attrs.get("State", {})
                    status = c_state.get("Status", "running")
                    health_obj = c_state.get("Health", {})
                    health_status = health_obj.get("Status", "healthy" if status == "running" else "unknown")

                    stats_data = await loop.run_in_executor(
                        None,
                        lambda c=container: c.stats(stream=False),
                    )
                    cpu_percent, mem_percent, mem_mb = self._calculate_usage(stats_data)

                    metrics_aggregator.record_container_resources(
                        container_name=container.name,
                        cpu_percent=cpu_percent,
                        memory_percent=mem_percent,
                        memory_mb=mem_mb,
                        status=status,
                        health=health_status,
                    )

                    # Alerte proactive si saturation mémoire
                    if mem_percent >= settings.memory_alert_threshold_percent:
                        await dispatcher.send_critical_alert(
                            container_name=container.name,
                            reason=f"⚠️ Saturation Mémoire Élevée ({mem_percent}% / {round(mem_mb, 1)} MB)",
                            details=f"Seuil d'alerte défini à {settings.memory_alert_threshold_percent}%. Risque d'OOM imminent.",
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[DockerCollector] Erreur collecte métriques ressources : {e}")

            await asyncio.sleep(60)

    @staticmethod
    def _calculate_usage(stats: dict) -> tuple[float, float, float]:
        """Calcule le % CPU, % Mémoire et l'utilisation RAM en MB."""
        try:
            # Calcul RAM
            memory_stats = stats.get("memory_stats", {})
            mem_usage = memory_stats.get("usage", 0)
            mem_limit = memory_stats.get("limit", 1)
            mem_mb = mem_usage / (1024 * 1024)
            mem_percent = round((mem_usage / mem_limit) * 100, 1) if mem_limit > 0 else 0.0

            # Calcul CPU
            cpu_stats = stats.get("cpu_stats", {})
            precpu_stats = stats.get("precpu_stats", {})
            cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - precpu_stats.get("cpu_usage", {}).get("total_usage", 0)
            system_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get("system_cpu_usage", 0)
            online_cpus = cpu_stats.get("online_cpus", len(cpu_stats.get("cpu_usage", {}).get("percpu_usage", []) or [1]))

            cpu_percent = 0.0
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = round((cpu_delta / system_delta) * online_cpus * 100.0, 1)

            return cpu_percent, mem_percent, mem_mb
        except Exception:
            return 0.0, 0.0, 0.0


docker_collector = DockerCollector()
