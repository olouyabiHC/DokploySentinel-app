"""Unit tests for LogParser."""

import pytest
from src.analyzers.log_parser import LogParser


def test_parse_http_access_success():
    line = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "POST /dashboard/autonome/tests/attempt/20970/submit/ HTTP/1.1" 200 122 "https://example.com" "Mozilla/5.0" 80202'
    entry = LogParser.parse_line(line, container_name="bestlens-app")

    assert entry.is_http_request is True
    assert entry.http_method == "POST"
    assert entry.http_path == "/dashboard/autonome/tests/attempt/20970/submit/"
    assert entry.status_code == 200
    assert entry.is_error is False
    assert entry.latency_ms == pytest.approx(80.20, 0.01)


def test_parse_http_access_500_error():
    line = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "GET /api/v1/checkout/ HTTP/1.1" 500 520 "https://example.com" "Mozilla/5.0" 1500'
    entry = LogParser.parse_line(line, container_name="bestlens-app")

    assert entry.is_http_request is True
    assert entry.status_code == 500
    assert entry.is_error is True
    assert "HTTP 500" in entry.error_message


def test_parse_http_access_429_rate_limit():
    line = '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "GET /api/v1/search HTTP/1.1" 429 20 "https://example.com" "Mozilla/5.0" 20'
    entry = LogParser.parse_line(line, container_name="api-gateway")

    assert entry.is_http_request is True
    assert entry.status_code == 429
    assert entry.is_error is True
    assert "Rate Limit (429)" in entry.error_message


def test_parse_uvicorn_log():
    line = 'INFO: 192.168.1.50:54321 - "POST /api/v1/users HTTP/1.1" 201 Created - 45.2ms'
    entry = LogParser.parse_line(line, container_name="fastapi-app")

    assert entry.is_http_request is True
    assert entry.http_method == "POST"
    assert entry.http_path == "/api/v1/users"
    assert entry.status_code == 201
    assert entry.latency_ms == 45.2


def test_parse_json_log_http():
    line = '{"level": "info", "method": "GET", "path": "/api/v1/items", "status": 200, "duration": 12.5}'
    entry = LogParser.parse_line(line, container_name="node-microservice")

    assert entry.is_http_request is True
    assert entry.http_method == "GET"
    assert entry.http_path == "/api/v1/items"
    assert entry.status_code == 200
    assert entry.latency_ms == 12.5
    assert entry.is_error is False


def test_parse_json_log_error():
    line = '{"level": "error", "message": "Database connection pool exhausted", "service": "auth-service"}'
    entry = LogParser.parse_line(line, container_name="auth-service")

    assert entry.is_error is True
    assert "Database connection pool exhausted" in entry.error_message


def test_parse_critical_python_traceback():
    line = 'Traceback (most recent call last):\n  File "views.py", line 45, in get'
    entry = LogParser.parse_line(line, container_name="my-app")

    assert entry.is_critical_exception is True
    assert entry.is_error is True


def test_parse_critical_node_unhandled_rejection():
    line = 'UnhandledPromiseRejectionWarning: Unhandled promise rejection (rejection id: 1): Error: connect ECONNREFUSED 127.0.0.1:6379'
    entry = LogParser.parse_line(line, container_name="node-worker")

    assert entry.is_critical_exception is True
    assert entry.is_error is True


def test_parse_critical_go_panic():
    line = 'panic: runtime error: invalid memory address or nil pointer dereference'
    entry = LogParser.parse_line(line, container_name="go-service")

    assert entry.is_critical_exception is True
    assert entry.is_error is True
