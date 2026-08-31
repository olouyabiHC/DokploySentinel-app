"""Aggregates log metrics per container over time for periodic digest generation."""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime, timezone
import statistics

from src.analyzers.log_parser import ParsedLogEntry


@dataclass
class ContainerStats:
    container_name: str
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
                # Conserver au maximum les 15 dernières exceptions uniques
                if len(self.critical_exceptions) < 15:
                    self.critical_exceptions.append(entry.error_message)

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


class MetricsAggregator:
    def __init__(self):
        self._stats: Dict[str, ContainerStats] = defaultdict(lambda: ContainerStats(container_name=""))

    def get_or_create(self, container_name: str) -> ContainerStats:
        if container_name not in self._stats:
            self._stats[container_name] = ContainerStats(container_name=container_name)
        return self._stats[container_name]

    def record(self, entry: ParsedLogEntry, latency_threshold_ms: float = 2000.0):
        stats = self.get_or_create(entry.container_name)
        stats.record_entry(entry, latency_threshold_ms)

    def get_all_stats(self) -> Dict[str, ContainerStats]:
        return dict(self._stats)

    def reset_stats(self):
        """Réinitialise les statistiques pour le prochain cycle de digest."""
        self._stats.clear()


metrics_aggregator = MetricsAggregator()
