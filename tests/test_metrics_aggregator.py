"""Unit tests for MetricsAggregator and ContainerStats."""

import pytest
from src.analyzers.log_parser import LogParser
from src.analyzers.metrics_aggregator import MetricsAggregator, ContainerStats


def test_metrics_aggregator_counts_and_rates():
    aggregator = MetricsAggregator()

    line_200 = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "GET /home HTTP/1.1" 200 122 "ref" "ua" 50'
    line_404 = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "GET /missing HTTP/1.1" 404 122 "ref" "ua" 20'
    line_500 = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "POST /checkout HTTP/1.1" 500 122 "ref" "ua" 2500'

    for line in [line_200, line_200, line_404, line_500]:
        entry = LogParser.parse_line(line, "api-service")
        aggregator.record(entry, latency_threshold_ms=2000.0)

    stats = aggregator.get_or_create("api-service")
    assert stats.total_requests == 4
    assert stats.count_2xx == 2
    assert stats.count_4xx == 1
    assert stats.count_5xx == 1
    assert stats.error_5xx_rate_percent == 25.0
    assert len(stats.slow_requests) == 1
    assert stats.slow_requests[0]["path"] == "/checkout"


def test_metrics_aggregator_latencies():
    stats = ContainerStats(container_name="test-app")
    stats.latencies_ms = [10.0, 20.0, 30.0, 40.0, 100.0]

    assert stats.median_latency_ms == 30.0
    assert stats.p95_latency_ms == 100.0


def test_metrics_aggregator_resources():
    aggregator = MetricsAggregator()
    aggregator.record_container_resources(
        container_name="web-app",
        cpu_percent=12.5,
        memory_percent=45.0,
        memory_mb=256.0,
        status="running",
        health="healthy",
    )
    aggregator.record_container_resources(
        container_name="web-app",
        cpu_percent=25.5,
        memory_percent=55.0,
        memory_mb=312.0,
        status="running",
        health="healthy",
    )

    stats = aggregator.get_or_create("web-app")
    assert stats.avg_cpu_percent == 19.0
    assert stats.max_memory_percent == 55.0
    assert stats.max_memory_mb == 312.0
    assert stats.docker_status == "running"
    assert stats.health_status == "healthy"


def test_metrics_aggregator_reset():
    aggregator = MetricsAggregator()
    entry = LogParser.parse_line('127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "GET / HTTP/1.1" 200 122 "ref" "ua" 50', "app-1")
    aggregator.record(entry)

    assert aggregator.get_or_create("app-1").total_requests == 1
    aggregator.reset_stats()

    stats = aggregator.get_or_create("app-1")
    assert stats.total_requests == 0
    assert stats.latencies_ms == []
