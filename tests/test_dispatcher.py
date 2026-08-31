"""Unit tests for NotificationDispatcher and anti-spam throttling."""

import pytest
from unittest.mock import AsyncMock, patch
from src.notifiers.dispatcher import NotificationDispatcher
from src.analyzers.metrics_aggregator import ContainerStats


@pytest.mark.asyncio
async def test_antispam_cooldown_throttles_duplicate_alerts():
    dispatcher = NotificationDispatcher()
    dispatcher.telegram.send_message = AsyncMock(return_value=True)
    dispatcher.discord.send_embed = AsyncMock(return_value=True)

    # Premier envoi : passe
    await dispatcher.send_critical_alert("app-a", "OOMKilled", "Details 1")
    assert dispatcher.telegram.send_message.call_count == 1

    # Deuxième envoi immédiat pour la même raison : bloqué par le cooldown anti-spam
    await dispatcher.send_critical_alert("app-a", "OOMKilled", "Details 2")
    assert dispatcher.telegram.send_message.call_count == 1

    # Alerte pour un autre conteneur : passe
    await dispatcher.send_critical_alert("app-b", "OOMKilled", "Details 3")
    assert dispatcher.telegram.send_message.call_count == 2


@pytest.mark.asyncio
async def test_periodic_digest_dispatch():
    dispatcher = NotificationDispatcher()
    dispatcher.telegram.send_message = AsyncMock(return_value=True)
    dispatcher.discord.send_embed = AsyncMock(return_value=True)
    dispatcher.whatsapp.send_message = AsyncMock(return_value=True)
    dispatcher.email.send_email = AsyncMock(return_value=True)

    stats_map = {
        "api-prod": ContainerStats(
            container_name="api-prod",
            total_requests=100,
            count_2xx=95,
            count_4xx=5,
            count_5xx=0,
            latencies_ms=[50.0, 60.0],
        )
    }

    await dispatcher.send_periodic_digest(stats_map, period_hours=3)

    assert dispatcher.telegram.send_message.called
    assert dispatcher.discord.send_embed.called
    assert dispatcher.whatsapp.send_message.called
    assert dispatcher.email.send_email.called


@pytest.mark.asyncio
async def test_notification_channels_testing():
    dispatcher = NotificationDispatcher()
    dispatcher.telegram.send_message = AsyncMock(return_value=True)
    dispatcher.discord.send_embed = AsyncMock(return_value=True)
    dispatcher.whatsapp.send_message = AsyncMock(return_value=True)
    dispatcher.email.send_email = AsyncMock(return_value=True)

    results = await dispatcher.test_notifications("all")
    assert results.get("telegram") is True
    assert results.get("discord") is True
    assert results.get("whatsapp") is True
    assert results.get("email") is True
