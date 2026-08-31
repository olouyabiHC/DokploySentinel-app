"""Aggregates log metrics, performance, and resource stats per container and per server/VPS."""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import statistics

from src.analyzers.log_parser import ParsedLogEntry


@dataclass
class ServerInfo:
    server_name: str
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    host_cpu_percent: float = 0.0
    host_memory_percent: float = 0.0
    host_disk_percent: float = 0.0
    status: str = "online"
    alerted_offline: bool = False


@dataclass
class ContainerStats:
    container_name: str
    server_name: str = "local"
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_requests: int = 0
    count_2xx: int = 0
    count_3xx: int = 0
    count_4xx: int = 0
    count_5xx: int = 0
    latencies_ms: List[float] = field(default_factory=list)
    critical_exceptions: List[str] = field(default_factory=list)
    slow_requests: List[Dict] = field(default_factory=list)
    cpu_samples: List[float] = field(default_factory=list)
    memory_samples: List[float] = field(default_factory=list)
    max_memory_mb: float = 0.0
    docker_status: str = "running"
    health_status: str = "healthy"

    def record_entry(self, entry: ParsedLogEntry, latency_threshold_ms: float = 2000.0):
        self.last_seen = datetime.now(timezone.utc)

        if entry.is_http_request:
            self.total_requests += 1
            if entry.status_code:
                if 200 <= entry.status_code < 300:
                    self.count_2xx += 1
                elif 300 <= entry.status_code < 400:
                    self.count_3xx += 1
                elif 400 <= entry.status_code < 500:
                    self.count_4xx += 1
                elif entry.status_code >= 500:
                    self.count_5xx += 1

            if entry.latency_ms is not None:
                self.latencies_ms.append(entry.latency_ms)
                if entry.latency_ms >= latency_threshold_ms:
                    self.slow_requests.append({
                        "method": entry.http_method,
                        "path": entry.http_path,
                        "latency_ms": round(entry.latency_ms, 1),
                        "status": entry.status_code,
                        "timestamp": self.last_seen.isoformat(),
                    })

        if entry.is_critical_exception and entry.error_message:
            if entry.error_message not in self.critical_exceptions:
                if len(self.critical_exceptions) < 15:
                    self.critical_exceptions.append(entry.error_message)

    def record_resources(
        self,
        cpu_percent: float,
        memory_percent: float,
        memory_mb: float,
        status: str = "running",
        health: str = "healthy",
    ):
        self.cpu_samples.append(cpu_percent)
        self.memory_samples.append(memory_percent)
        if memory_mb > self.max_memory_mb:
            self.max_memory_mb = round(memory_mb, 1)
        self.docker_status = status
        self.health_status = health

    @property
    def error_5xx_rate_percent(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round((self.count_5xx / self.total_requests) * 100, 2)

    @property
    def median_latency_ms(self) -> Optional[float]:
        if not self.latencies_ms:
            return None
        return round(statistics.median(self.latencies_ms), 1)

    @property
    def p95_latency_ms(self) -> Optional[float]:
        if not self.latencies_ms:
            return None
        sorted_lat = sorted(self.latencies_ms)
        idx = int(len(sorted_lat) * 0.95)
        return round(sorted_lat[min(idx, len(sorted_lat) - 1)], 1)

    @property
    def avg_cpu_percent(self) -> Optional[float]:
        if not self.cpu_samples:
            return None
        return round(sum(self.cpu_samples) / len(self.cpu_samples), 1)

    @property
    def max_memory_percent(self) -> Optional[float]:
        if not self.memory_samples:
            return None
        return round(max(self.memory_samples), 1)


class MetricsAggregator:
    def __init__(self):
        # Clé composite: (server_name, container_name) -> ContainerStats
        self._stats: Dict[Tuple[str, str], ContainerStats] = {}
        # Suivi de la santé globale des serveurs connectés
        self._servers: Dict[str, ServerInfo] = {}

    def get_or_create(self, container_name: str, server_name: str = "local") -> ContainerStats:
        key = (server_name, container_name)
        if key not in self._stats:
            self._stats[key] = ContainerStats(container_name=container_name, server_name=server_name)
        # Enregistrer aussi le serveur s'il n'est pas encore répertorié
        if server_name not in self._servers:
            self._servers[server_name] = ServerInfo(server_name=server_name)
        return self._stats[key]

    def record(self, entry: ParsedLogEntry, latency_threshold_ms: float = 2000.0, server_name: str = "local"):
        stats = self.get_or_create(entry.container_name, server_name=server_name)
        stats.record_entry(entry, latency_threshold_ms)

    def record_container_resources(
        self,
        container_name: str,
        cpu_percent: float,
        memory_percent: float,
        memory_mb: float,
        status: str = "running",
        health: str = "healthy",
        server_name: str = "local",
    ):
        stats = self.get_or_create(container_name, server_name=server_name)
        stats.record_resources(cpu_percent, memory_percent, memory_mb, status, health)

    def record_server_heartbeat(
        self,
        server_name: str,
        host_cpu: float = 0.0,
        host_memory: float = 0.0,
        host_disk: float = 0.0,
    ):
        """Enregistre le battement de cœur (heartbeat) et les métriques globales d'un VPS."""
        if server_name not in self._servers:
            self._servers[server_name] = ServerInfo(server_name=server_name)
        srv = self._servers[server_name]
        srv.last_heartbeat = datetime.now(timezone.utc)
        srv.host_cpu_percent = host_cpu
        srv.host_memory_percent = host_memory
        srv.host_disk_percent = host_disk
        srv.status = "online"
        srv.alerted_offline = False

    def get_all_stats(self) -> Dict[Tuple[str, str], ContainerStats]:
        return dict(self._stats)

    def get_stats_grouped_by_server(self) -> Dict[str, Dict[str, ContainerStats]]:
        """Retourne les métriques regroupées par nom de serveur."""
        grouped: Dict[str, Dict[str, ContainerStats]] = defaultdict(dict)
        for (server_name, container_name), stats in self._stats.items():
            grouped[server_name][container_name] = stats
        return dict(grouped)

    def get_servers_overview(self) -> List[Dict]:
        """Retourne un état synthétique de tous les serveurs VPS répertoriés."""
        overview = []
        now = datetime.now(timezone.utc)
        for s_name, srv in self._servers.items():
            # Compter les conteneurs associés
            containers_count = sum(1 for (sn, _) in self._stats.keys() if sn == s_name)
            elapsed_sec = (now - srv.last_heartbeat).total_seconds()
            overview.append({
                "server_name": s_name,
                "status": "online" if elapsed_sec < 180 else "offline",
                "last_heartbeat": srv.last_heartbeat.isoformat(),
                "seconds_since_last_seen": int(elapsed_sec),
                "host_cpu_percent": srv.host_cpu_percent,
                "host_memory_percent": srv.host_memory_percent,
                "host_disk_percent": srv.host_disk_percent,
                "containers_count": containers_count,
            })
        return overview

    def reset_stats(self):
        """Réinitialise les accumulateurs de trafic pour le prochain cycle de digest."""
        for (server_name, container_name), s in list(self._stats.items()):
            self._stats[(server_name, container_name)] = ContainerStats(
                container_name=container_name,
                server_name=server_name,
                docker_status=s.docker_status,
                health_status=s.health_status,
            )


metrics_aggregator = MetricsAggregator()
