"""
Tests for Bot App wiring and handlers.
"""
import pytest
from src.config import Settings
from src.bot.bot_app import create_bot_and_dispatcher
from src.core.pipeline import PipelineManager


def test_create_bot_and_dispatcher():
    settings = Settings(
        BOT_TOKEN="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
        ALLOWED_USER_IDS="111,222"
    )
    bot, dp = create_bot_and_dispatcher(settings=settings)
    assert bot is not None
    assert dp is not None
    assert "pipeline" in dp.workflow_data
    assert "crawler" in dp.workflow_data
    assert "disk_guard" in dp.workflow_data
