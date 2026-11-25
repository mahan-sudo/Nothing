"""ناظر: هر چند ثانیه نگاه می‌کنه کدوم حساب‌ها باید روشن باشن (متصل + سلف روشن + اشتراک فعال)
و برای هرکدوم یک AccountRuntime بالا می‌یاره یا خاموش می‌کنه. همه‌چیز از دیتابیس خونده می‌شه،
پس دکمه‌ی روشن/خاموش پنل و تمدید اشتراک خودکار اثر می‌کنن و بعد از ری‌استارت هم چیزی گم نمی‌شه."""
from __future__ import annotations

import asyncio
import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from ..config import RECONCILE_SECONDS, Settings
from ..crypto import Vault
from ..utils import utcnow
from . import store
from .runtime import AccountRuntime

log = logging.getLogger(__name__)

MAX_STARTS_PER_CYCLE = 5
HEALTH_EVERY_SECONDS = 300


class Supervisor:
    def __init__(self, bot: Bot, db, settings: Settings, vault: Vault) -> None:
        self.bot, self.db, self.settings, self.vault = bot, db, settings, vault
        self.runtimes: dict[int, AccountRuntime] = {}
        self._bad_cycles: dict[int, int] = {}
        self._notified: dict[str, float] = {}
        self._last_health = time.monotonic()

    # ------------------------------------------------------------ اعلان به کاربر
    async def notify(self, user_id: int, text: str, key: str, cooldown: int = 3600) -> None:
        k = f"{user_id}:{key}"
        now = time.monotonic()
        if now - self._notified.get(k, -1e9) < cooldown:
            return
        self._notified[k] = now
        try:
            await self.bot.send_message(user_id, text)
        except TelegramAPIError:
            log.info("could not notify user %s", user_id)

    async def account_dead(self, user_id: int, text: str) -> None:
        await store.mark_account_dead(self.db, user_id)
        await self.notify(user_id, text, key="dead", cooldown=60)

    # ------------------------------------------------------------ حلقه‌ی اصلی
    async def run(self) -> None:
        log.info("self engine started")
        while True:
            try:
                await self.reconcile()
                if time.monotonic() - self._last_health > HEALTH_EVERY_SECONDS:
                    self._last_health = time.monotonic()
                    for rt in list(self.runtimes.values()):
                        await rt.health_check()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("supervisor error")
            await asyncio.sleep(RECONCILE_SECONDS)

    async def reconcile(self) -> None:
        wanted = await store.runnable_accounts(self.db, utcnow())

        for uid, rt in list(self.runtimes.items()):
            stale = uid not in wanted or rt.session_enc != wanted[uid]
            if not stale and not rt.is_connected():
                self._bad_cycles[uid] = self._bad_cycles.get(uid, 0) + 1
                stale = self._bad_cycles[uid] >= 2  # دو دور پشت‌سرهم قطع بود → دوباره بالا بیار
            else:
                self._bad_cycles.pop(uid, None)
            if stale:
                self.runtimes.pop(uid, None)
                self._bad_cycles.pop(uid, None)
                await rt.stop()

        started = 0
        for uid, enc in wanted.items():
            if uid in self.runtimes or started >= MAX_STARTS_PER_CYCLE:
                continue
            started += 1
            try:
                session_string = self.vault.decrypt(enc)
            except Exception:
                log.error("cannot decrypt session for user %s (was ENCRYPTION_SECRET changed?)", uid)
                continue
            rt = AccountRuntime(self, uid, enc, session_string)
            session_string = ""
            try:
                ok = await rt.start()
            except Exception:
                log.exception("runtime start failed for user %s", uid)
                await rt.stop()
                continue
            if ok:
                self.runtimes[uid] = rt
            else:
                await rt.stop()

    async def stop(self) -> None:
        for rt in list(self.runtimes.values()):
            await rt.stop()
        self.runtimes.clear()
