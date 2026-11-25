from __future__ import annotations

import logging

from aiogram import BaseMiddleware
from aiogram.types import Message
from redis.exceptions import RedisError

from ..services.users import ensure_user

log = logging.getLogger(__name__)


class EnsureUserMiddleware(BaseMiddleware):
    """مطمئن می‌شه کاربر توی دیتابیس هست. (/start خودش این کار رو با ثبت دعوت‌کننده انجام می‌ده.)
    Redis فقط یادش می‌مونه «این کاربر وجود داره»؛ هیچ داده‌ی مالی‌ای کش نمی‌شه."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user is not None and not user.is_bot:
            is_start = isinstance(event, Message) and (event.text or "").startswith("/start")
            if not is_start:
                redis, db = data["redis"], data["db"]
                key = f"known:{user.id}"
                known = None
                try:
                    known = await redis.get(key)
                except RedisError:
                    log.warning("redis unavailable in EnsureUserMiddleware", exc_info=True)
                if not known:
                    async with db.begin() as session:
                        await ensure_user(session, user)
                    try:
                        await redis.set(key, "1", ex=600)
                    except RedisError:
                        pass
        return await handler(event, data)
