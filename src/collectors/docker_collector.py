"""Docker log and container lifecycle collector."""

import asyncio
import logging
import docker
from typing import Set

from src.config import settings
from src.analyzers.log_parser import LogParser
from src.analyzers.metrics_aggregator import metrics_aggregator
from src.notifiers.dispatcher import dispatcher

logger = logging.getLogger(__name__)


class DockerCollector:
    def __init__(self):
        self.client = None
        self.running = False
        self._active_tasks: Set[asyncio.Task] = set()

    def connect(self) -> bool:
        try:
            self.client = docker.DockerClient(base_url=settings.docker_socket_path)
            self.client.ping()
            logger.info("[DockerCollector] Connecté avec succès au démon Docker.")
            return True
        except Exception as e:
            logger.warning(f"[DockerCollector] Impossible de se connecter au socket Docker ({settings.docker_socket_path}) : {e}")
            logger.info("[DockerCollector] Mode autonome actif (en attente de conteneurs ou webhooks).")
            return False

    def should_monitor_container(self, container_name: str) -> bool:
        name_lower = container_name.lower()

        # Vérifier si dans les conteneurs ignorés
        for ignored in settings.ignored_patterns_list:
            if ignored in name_lower:
                return False

        # Si liste de filtres définie
        if settings.monitored_patterns_list:
            return any(mon in name_lower for mon in settings.monitored_patterns_list)

        return True

    async def start(self):
        self.running = True
        if not self.connect():
            return

        # 1. Démarrer l'écoute des événements de cycle de vie (crash, restart, OOM)
        event_task = asyncio.create_task(self._listen_docker_events())
        self._active_tasks.add(event_task)

        # 2. Démarrer la surveillance des logs pour les conteneurs existants
        log_task = asyncio.create_task(self._monitor_containers_logs())
        self._active_tasks.add(log_task)

    async def stop(self):
        self.running = False
        for task in self._active_tasks:
            task.cancel()
        logger.info("[DockerCollector] Arrêté.")

    async def _listen_docker_events(self):
        """Surveille les événements Docker en temps réel (arrêt brutal, OOM, crash)."""
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                events = await loop.run_in_executor(
                    None,
                    lambda: self.client.events(decode=True, filters={"type": "container"})
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

                    # Détection OOMKilled ou die anormal
                    if action == "oom":
                        await dispatcher.send_critical_alert(
                            container_name=container_name,
                            reason="💥 Out Of Memory (OOMKilled) — Le conteneur a dépassé sa limite de RAM !",
                            details=str(attributes)
                        )
                    elif action == "die":
                        exit_code = attributes.get("exitCode")
                        if exit_code and exit_code != "0":
                            await dispatcher.send_critical_alert(
                                container_name=container_name,
                                reason=f"🛑 Arrêt anormal du conteneur (Exit Code: {exit_code})",
                                details=f"Événement: {action} | ExitCode: {exit_code}"
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DockerCollector] Erreur boucle événements Docker : {e}")
                await asyncio.sleep(5)

    async def _monitor_containers_logs(self):
        """Scanne périodiquement les logs récents de chaque conteneur."""
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                containers = await loop.run_in_executor(None, self.client.containers.list)
                for container in containers:
                    if not self.should_monitor_container(container.name):
                        continue

                    # Récupérer les logs des 30 dernières secondes
                    raw_logs = await loop.run_in_executor(
                        None,
                        lambda c=container: c.logs(since=30, timestamps=False).decode("utf-8", errors="replace")
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
                                details=entry.raw_line
                            )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DockerCollector] Erreur scan des logs : {e}")

            await asyncio.sleep(30)


docker_collector = DockerCollector()
