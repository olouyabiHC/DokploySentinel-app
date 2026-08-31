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
        assert data["version"] == "2.0.0"


@pytest.mark.asyncio
async def test_stats_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "servers_count" in data
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
async def test_agent_sync_endpoint():
    settings.debug = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "server_name": "VPS-Client-AutoEcole",
            "host_cpu_percent": 15.2,
            "host_memory_percent": 42.0,
            "host_disk_percent": 35.0,
            "containers": [
                {
                    "container_name": "api-autoecole",
                    "cpu_percent": 5.0,
                    "memory_percent": 20.0,
                    "memory_mb": 128.0,
                    "status": "running",
                    "health": "healthy",
                }
            ],
            "logs": [
                '127.0.0.1 - - [31/Aug/2026:12:00:00 +0100] "GET /api/v1/lessons HTTP/1.1" 200 122 "ref" "ua" 45',
            ],
            "alerts": [],
        }
        response = await ac.post("/api/v1/agent/sync", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["server_name"] == "VPS-Client-AutoEcole"
        assert data["processed_containers"] == 1


@pytest.mark.asyncio
async def test_servers_overview_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/servers")
        assert response.status_code == 200
        data = response.json()
        assert "servers" in data


@pytest.mark.asyncio
async def test_uptime_overview_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/uptime")
        assert response.status_code == 200
        data = response.json()
        assert "targets" in data


@pytest.mark.asyncio
async def test_telegram_webhook_endpoint():
    settings.debug = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "message": {
                "text": "/help",
                "chat": {"id": 123456789},
                "from": {"username": "test_admin"},
            }
        }
        response = await ac.post("/api/v1/telegram/webhook", json=payload)
        assert response.status_code == 200
        assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_mutes_rest_api():
    settings.debug = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Create Mute
        post_resp = await ac.post("/api/v1/mutes", json={"pattern": "wordpress-test", "duration_minutes": 60})
        assert post_resp.status_code == 200
        assert post_resp.json()["status"] == "success"

        # 2. Get Mutes
        get_resp = await ac.get("/api/v1/mutes")
        assert get_resp.status_code == 200
        patterns = [m["pattern"] for m in get_resp.json()["active_mutes"]]
        assert "wordpress-test" in patterns

        # 3. Delete Mute
        del_resp = await ac.delete("/api/v1/mutes/wordpress-test")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_ai_diagnose_endpoint():
    settings.debug = True
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        payload = {
            "container_name": "wordpress-test",
            "reason": "PHP Fatal Error",
            "details": "PHP Fatal error: Uncaught Error: Undefined constant 'ABSPATH' in /var/www/html/wp-settings.php:34",
        }
        response = await ac.post("/api/v1/ai/diagnose", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "diagnosis" in data
        assert data["diagnosis"]["category"] == "BOT_SCANNER"


@pytest.mark.asyncio
async def test_logs_ingest_endpoint():
    settings.debug = True
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
