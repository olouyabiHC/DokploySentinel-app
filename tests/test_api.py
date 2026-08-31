"""Integration tests for FastAPI endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app
from src.config import settings


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["app"] == "DokploySentinel"


@pytest.mark.asyncio
async def test_stats_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "monitored_containers" in data
        assert "stats" in data


@pytest.mark.asyncio
async def test_containers_overview_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/containers")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "containers" in data


@pytest.mark.asyncio
async def test_logs_ingest_endpoint():
    settings.debug = True  # Permet de bypasser la clé secrète en mode test
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "container_name": "direct-app",
            "lines": [
                '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "GET /api/v1/health HTTP/1.1" 200 122 "ref" "ua" 50',
                '127.0.0.1 - - [31/Aug/2026:07:06:04 +0100] "POST /api/v1/pay HTTP/1.1" 500 122 "ref" "ua" 150',
            ],
        }
        response = await ac.post("/api/v1/logs/ingest", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["processed_lines"] == 2


@pytest.mark.asyncio
async def test_dokploy_webhook_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "event": "deployment.success",
            "title": "bestlens-app",
            "message": "Déploiement réussi sur Dokploy",
        }
        response = await ac.post("/api/v1/webhooks/dokploy", json=payload)
        assert response.status_code == 200
        assert response.json()["status"] == "received"
