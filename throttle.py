from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from ..cache import hit


class ThrottleMiddleware(BaseMiddleware):
    """جلوی اسپم رو می‌گیره: حداکثر 20 پیام یا کلیک در هر 10 ثانیه برای هر کاربر."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is not None:
            ok = await hit(data["redis"], f"rl:{user.id}", limit=20, window=10)
            if not ok:
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer("یه کم آروم‌تر 🌱")
                    except Exception:
                        pass
                return None
        return await handler(event, data)
