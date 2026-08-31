"""Unit tests for LogParser and MetricsAggregator."""

import pytest
from src.analyzers.log_parser import LogParser
from src.analyzers.metrics_aggregator import MetricsAggregator


def test_parse_http_access_success():
    line = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "POST /dashboard/autonome/tests/attempt/20970/submit/ HTTP/1.1" 200 122 "https://example.com" "Mozilla/5.0" 80202'
    entry = LogParser.parse_line(line, container_name="bestlens-app")

    assert entry.is_http_request is True
    assert entry.http_method == "POST"
    assert entry.http_path == "/dashboard/autonome/tests/attempt/20970/submit/"
    assert entry.status_code == 200
    assert entry.is_error is False
    assert entry.latency_ms == pytest.approx(80.202, 0.01)


def test_parse_http_access_500_error():
    line = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "GET /api/v1/checkout/ HTTP/1.1" 500 520 "https://example.com" "Mozilla/5.0" 1500'
    entry = LogParser.parse_line(line, container_name="bestlens-app")

    assert entry.is_http_request is True
    assert entry.status_code == 500
    assert entry.is_error is True
    assert "HTTP 500" in entry.error_message


def test_parse_critical_exception():
    line = 'Traceback (most recent call last):\n  File "views.py", line 45, in get'
    entry = LogParser.parse_line(line, container_name="my-app")

    assert entry.is_critical_exception is True
    assert entry.is_error is True


def test_metrics_aggregator():
    aggregator = MetricsAggregator()
    
    line1 = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "GET /home/ HTTP/1.1" 200 122 "ref" "ua" 20000'
    line2 = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "GET /broken/ HTTP/1.1" 500 122 "ref" "ua" 50000'
    
    entry1 = LogParser.parse_line(line1, "app-1")
    entry2 = LogParser.parse_line(line2, "app-1")
    
    aggregator.record(entry1)
    aggregator.record(entry2)
    
    stats = aggregator.get_or_create("app-1")
    assert stats.total_requests == 2
    assert stats.count_2xx == 1
    assert stats.count_5xx == 1
    assert stats.error_5xx_rate_percent == 50.0
