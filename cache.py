"""ابزارهای Redis. فقط برای چیزهای کم‌خطر: محدودیت نرخ و قفل کوتاه.

قانون: Redis هیچ‌وقت منبع حقیقت نیست. موجودی، اشتراک و پرداخت‌ها فقط از دیتابیس خونده می‌شن.
اگه Redis قطع بشه، ربات کار می‌کنه (فقط محدودیت نرخ موقتاً غیرفعاله) و صحت پول به دیتابیس بستگی داره.
"""
from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

log = logging.getLogger(__name__)


async def hit(redis: Redis, key: str, limit: int, window: int) -> bool:
    """True یعنی مجازه. بعد از limit بار در window ثانیه False می‌شه."""
    try:
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = await pipe.execute()
        if count == 1 or ttl < 0:
            await redis.expire(key, window)
        return int(count) <= limit
    except RedisError:
        log.warning("redis unavailable in hit()", exc_info=True)
        return True


async def try_lock(redis: Redis, key: str, ttl: int) -> bool:
    """قفل کوتاه برای جلوگیری از دوبار‌کلیک. (امنیت اصلی با قفل دیتابیسه.)"""
    try:
        return bool(await redis.set(key, "1", nx=True, ex=ttl))
    except RedisError:
        log.warning("redis unavailable in try_lock()", exc_info=True)
        return True
