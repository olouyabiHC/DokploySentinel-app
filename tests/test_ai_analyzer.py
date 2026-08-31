"""Unit tests for AIAnalyzer Root-Cause Analysis and Heuristic Engine."""

import pytest
from src.services.ai_analyzer import AIAnalyzer


@pytest.mark.asyncio
async def test_ai_analyzer_detects_wordpress_bot_scanner():
    details = (
        "[Sat Aug 29 15:36:11 2026] [php:error] PHP Fatal error: "
        'Uncaught Error: Undefined constant "ABSPATH" in /var/www/html/wp-settings.php:34'
    )
    result = await AIAnalyzer.analyze_incident(
        container_name="savanes-du-continent-wordpress-1",
        reason="PHP Fatal Error",
        details=details,
        server_name="VPS-Principal-Lekyn",
    )

    assert result["category"] == "BOT_SCANNER"
    assert "Cloudflare" in result["formatted_text"]
    assert "WordPress" in result["formatted_text"]


@pytest.mark.asyncio
async def test_ai_analyzer_detects_oom_killed():
    result = await AIAnalyzer.analyze_incident(
        container_name="bestlens-worker",
        reason="Out of Memory (OOMKilled)",
        details="Container killed by cgroups with exit code 137",
        server_name="VPS-BestLens-Prod",
    )

    assert result["category"] == "MEMORY_OOM"
    assert "RAM" in result["formatted_text"]


@pytest.mark.asyncio
async def test_ai_analyzer_detects_postgres_db_error():
    details = "psycopg2.OperationalError: could not connect to server: Connection refused on port 5432"
    result = await AIAnalyzer.analyze_incident(
        container_name="django-api",
        reason="Database Connection Error",
        details=details,
        server_name="VPS-Client-A",
    )

    assert result["category"] == "DATABASE_ERROR"
    assert "base de données" in result["formatted_text"]


@pytest.mark.asyncio
async def test_ai_analyzer_detects_django_python_exception():
    details = "Traceback (most recent call last):\n  File 'views.py', line 24\nKeyError: 'user_id'"
    result = await AIAnalyzer.analyze_incident(
        container_name="django-web",
        reason="Traceback Exception",
        details=details,
        server_name="VPS-Client-A",
    )

    assert result["category"] == "PYTHON_EXCEPTION"
    assert "KeyError" in result["formatted_text"]
