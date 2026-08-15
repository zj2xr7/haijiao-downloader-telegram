"""
Authorization whitelist middleware for Telegram Bot.
"""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from src.config import Settings, settings as default_settings
from src.utils.logger import logger


class AuthMiddleware(BaseMiddleware):
    """Intercepts and restricts bot usage to configured ALLOWED_USER_IDS."""

    def __init__(self, settings: Settings = default_settings):
        super().__init__()
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        allowed_ids = self.settings.allowed_user_id_list

        # If whitelist is empty, permit all users
        if not allowed_ids:
            return await handler(event, data)

        user = getattr(event, "from_user", None)
        user_id = user.id if user else None

        if user_id is None or user_id not in allowed_ids:
            logger.warning(f"Unauthorized access attempt blocked from Telegram user ID: {user_id}")
            if isinstance(event, CallbackQuery):
                await event.answer(f"⛔ 未授权操作 (ID: {user_id})", show_alert=True)
            elif hasattr(event, "answer"):
                await event.answer(f"⛔ 抱歉，您没有访问此机器人的权限。\n您的 Telegram ID 是: `{user_id}`")
            return None

        return await handler(event, data)
