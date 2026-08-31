"""Unit tests for interactive TelegramBotHandler commands and callbacks."""

import pytest
from unittest.mock import AsyncMock, patch
from src.services.telegram_bot_handler import TelegramBotHandler
from src.services.mutes_manager import mutes_manager


@pytest.mark.asyncio
async def test_telegram_bot_help_command():
    handler = TelegramBotHandler()
    handler.telegram.send_message = AsyncMock(return_value=True)

    update = {
        "message": {
            "text": "/help",
            "chat": {"id": 123456789},
            "from": {"username": "admin_user"},
        }
    }

    processed = await handler.process_update(update)
    assert processed is True
    assert handler.telegram.send_message.called
    args, kwargs = handler.telegram.send_message.call_args
    assert "MENU INTERACTIF" in args[0] or "MENU INTERACTIF" in kwargs.get("text", "")


@pytest.mark.asyncio
async def test_telegram_bot_mute_and_unmute_commands():
    handler = TelegramBotHandler()
    handler.telegram.send_message = AsyncMock(return_value=True)

    # 1. /mute wordpress 120m
    update_mute = {
        "message": {
            "text": "/mute wordpress 2h",
            "chat": {"id": 123456789},
            "from": {"username": "admin_user"},
        }
    }
    await handler.process_update(update_mute)
    assert mutes_manager.is_muted("association-nonvitcha-wordpress-1") is True

    # 2. /unmute wordpress
    update_unmute = {
        "message": {
            "text": "/unmute wordpress",
            "chat": {"id": 123456789},
            "from": {"username": "admin_user"},
        }
    }
    await handler.process_update(update_unmute)
    assert mutes_manager.is_muted("association-nonvitcha-wordpress-1") is False


@pytest.mark.asyncio
async def test_telegram_bot_callback_mute_button():
    handler = TelegramBotHandler()
    handler.telegram.answer_callback_query = AsyncMock(return_value=True)
    handler.telegram.edit_message_text = AsyncMock(return_value=True)

    cb_update = {
        "callback_query": {
            "id": "cb_123",
            "data": "mute:bestlens-app:60",
            "message": {"chat": {"id": 123456789}, "message_id": 999, "text": "Alerte Crash"},
            "from": {"username": "admin_user"},
        }
    }

    processed = await handler.process_update(cb_update)
    assert processed is True
    assert mutes_manager.is_muted("bestlens-app") is True
    assert handler.telegram.answer_callback_query.called
    assert handler.telegram.edit_message_text.called
