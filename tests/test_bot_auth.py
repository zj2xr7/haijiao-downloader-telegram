"""
Tests for Telegram Bot Auth Middleware and Keyboards.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.bot.middlewares.auth import AuthMiddleware
from src.bot.keyboards.inline import build_author_pages_keyboard, build_openlist_button
from src.config import Settings


@pytest.mark.asyncio
async def test_auth_middleware_blocks_unauthorized_user():
    settings = Settings(BOT_TOKEN="fake", ALLOWED_USER_IDS="100,200")
    middleware = AuthMiddleware(settings=settings)
    
    event = MagicMock()
    event.from_user.id = 999  # Unauthorized ID
    event.answer = AsyncMock()
    
    handler = AsyncMock()
    res = await middleware(handler, event, {})
    
    assert res is None
    handler.assert_not_called()
    event.answer.assert_called_once()


@pytest.mark.asyncio
async def test_auth_middleware_permits_authorized_user():
    settings = Settings(BOT_TOKEN="fake", ALLOWED_USER_IDS="100,200")
    middleware = AuthMiddleware(settings=settings)
    
    event = MagicMock()
    event.from_user.id = 100  # Authorized ID
    
    handler = AsyncMock(return_value="OK")
    res = await middleware(handler, event, {})
    
    assert res == "OK"
    handler.assert_called_once()


def test_build_keyboards():
    kb_author = build_author_pages_keyboard(author_id="u55", total_pages=5)
    assert len(kb_author.inline_keyboard) >= 4
    assert "author_dl:u55:1-1" == kb_author.inline_keyboard[0][0].callback_data
    
    kb_openlist = build_openlist_button("https://pan.example.com/item")
    assert kb_openlist.inline_keyboard[0][0].url == "https://pan.example.com/item"
