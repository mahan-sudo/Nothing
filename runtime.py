"""موتور اجرای سلف برای یک حساب: دستورها + زمان‌بندی دقیق ارسال بنرها."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import timedelta

from telethon import TelegramClient, events, utils
from telethon.errors import (
    AuthKeyUnregisteredError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    FileReferenceExpiredError,
    FloodWaitError,
    MessageNotModifiedError,
    RPCError,
    SessionRevokedError,
    SlowModeWaitError,
    UserBannedInChannelError,
    UserDeactivatedBanError,
    UserDeactivatedError,
    UserNotParticipantError,
)
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, InputPeerChannel, InputPeerChat, PeerChannel, PeerChat

from ..config import (
    ACCOUNT_MIN_GAP_SECONDS,
    FAIL_STREAK_LIMIT,
    MAX_ACTIVE_BANNERS,
    MAX_BANNER_INTERVAL,
    MIN_BANNER_INTERVAL,
    Settings,
)
from ..utils import _DIGITS, format_interval, utcnow
from . import store
from . import texts as W

log = logging.getLogger(__name__)

_FIX = str.maketrans({"ي": "ی", "ك": "ک", "\u200c": " ", "\u200f": "", "\u200e": ""})
_RE_TIME = re.compile(r"^تنظیم زمان بنر\s*[\"“”«»']?\s*(\d{1,12})\s*(ثانیه|دقیقه|ساعت)\s*[\"“”«»']?$")
_UNITS = {"ثانیه": 1, "دقیقه": 60, "ساعت": 3600}
_SIMPLE = {"تنظیم پشتیبان", "تنظیم بنر", "تبچی روشن", "تبچی خاموش", "حذف بنر"}

_DEAD_ERRORS = (AuthKeyUnregisteredError, SessionRevokedError, UserDeactivatedError, UserDeactivatedBanError)
_FORBIDDEN_ERRORS = (
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    UserNotParticipantError,
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_DIGITS).translate(_FIX)).strip()


def make_input_peer(chat_id: int, access_hash: int | None):
    real_id, kind = utils.resolve_id(chat_id)
    if kind is PeerChannel:
        return InputPeerChannel(real_id, access_hash or 0)
    if kind is PeerChat:
        return InputPeerChat(real_id)
    raise ValueError("unsupported chat type")


class AccountRuntime:
    def __init__(self, sup, user_id: int, session_enc: str, session_string: str) -> None:
        self.sup = sup
        self.user_id = user_id
        self.session_enc = session_enc
        self.db = sup.db
        self.client = TelegramClient(
            StringSession(session_string),
            sup.settings.telegram_api_id,
            sup.settings.telegram_api_hash,
            device_model="Self Assistant",
            system_version="Server",
            app_version="1.0",
            flood_sleep_threshold=0,  # فلود رو خودمون مدیریت می‌کنیم
            request_retries=3,
        )
        self._tasks: dict[int, asyncio.Task] = {}
        self._send_lock = asyncio.Lock()
        self._last_send = 0.0
        self._paused_until = 0.0
        self._cache: dict[tuple[int, int], tuple[object, float]] = {}
        self._dead = False

    # ------------------------------------------------------------ چرخه‌ی عمر
    async def start(self) -> bool:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            await self.sup.account_dead(self.user_id, W.DEAD_SESSION)
            return False
        self.client.add_event_handler(self._on_outgoing, events.NewMessage(outgoing=True))
        for b in await store.list_enabled(self.db, self.user_id):
            self.schedule(b.id)
        return True

    async def stop(self) -> None:
        for t in self._tasks.values():
            t.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        try:
            await self.client.disconnect()
        except Exception:
            pass

    def is_connected(self) -> bool:
        return self.client.is_connected()

    async def health_check(self) -> None:
        try:
            await self.client.get_me()
        except _DEAD_ERRORS as e:
            await self._handle_dead(e)
        except Exception:
            log.info("health check failed for user %s", self.user_id)

    async def _handle_dead(self, err: Exception) -> None:
        if self._dead:
            return
        self._dead = True
        text = W.BANNED_ACCOUNT if isinstance(err, (UserDeactivatedError, UserDeactivatedBanError)) else W.DEAD_SESSION
        await self.sup.account_dead(self.user_id, text)

    # ------------------------------------------------------------ دستورها
    async def _on_outgoing(self, event) -> None:
        try:
            raw = event.raw_text or ""
            if not raw or len(raw) > 80:
                return
            text = norm(raw)
            m = _RE_TIME.match(text)
            if m is None and text not in _SIMPLE:
                return
            if m:
                await self._cmd_interval(event, int(m.group(1)) * _UNITS[m.group(2)])
            elif text == "تنظیم پشتیبان":
                await self._cmd_backup(event)
            elif text == "تنظیم بنر":
                await self._cmd_set_banner(event)
            elif text == "تبچی روشن":
                await self._cmd_toggle(event, True)
            elif text == "تبچی خاموش":
                await self._cmd_toggle(event, False)
            elif text == "حذف بنر":
                await self._cmd_delete(event)
        except _DEAD_ERRORS as e:
            await self._handle_dead(e)
        except Exception:
            log.exception("command failed (user %s)", self.user_id)
            await self._reply(event, W.GENERIC_ERROR)

    @staticmethod
    async def _reply(event, text: str) -> None:
        try:
            await event.edit(text, parse_mode=None)
        except MessageNotModifiedError:
            pass
        except Exception:
            log.info("could not edit command message")

    @staticmethod
    def _is_group(chat) -> bool:
        return isinstance(chat, Chat) or (isinstance(chat, Channel) and bool(chat.megagroup))

    async def _cmd_backup(self, event) -> None:
        chat = await event.get_chat()
        if not (isinstance(chat, Channel) and chat.broadcast):
            await self._reply(event, W.BACKUP_MUST_BE_PRIVATE)
            return
        if chat.username or getattr(chat, "usernames", None):
            await self._reply(event, W.BACKUP_MUST_BE_PRIVATE)
            return
        if not (chat.creator or chat.admin_rights):
            await self._reply(event, W.BACKUP_NEED_ADMIN)
            return
        peer = await event.get_input_chat()
        await store.set_backup(self.db, self.user_id, event.chat_id, getattr(peer, "access_hash", None), chat.title)
        try:
            await event.delete()
        except Exception:
            pass
        await self.client.send_message(peer, W.backup_set(event.chat_id), parse_mode="html")

    async def _cmd_set_banner(self, event) -> None:
        chat = await event.get_chat()
        if not self._is_group(chat):
            await self._reply(event, W.ONLY_GROUPS)
            return
        backup = await store.get_backup(self.db, self.user_id)
        if backup is None:
            await self._reply(event, W.NEED_BACKUP)
            return
        reply = await event.get_reply_message()
        if reply is None:
            await self._reply(event, W.NEED_REPLY)
            return
        if not reply.out:
            await self._reply(event, W.ONLY_OWN)
            return
        backup_peer = make_input_peer(backup.channel_id, backup.access_hash)
        try:
            copy = await self.client.send_message(backup_peer, reply)
        except _FORBIDDEN_ERRORS:
            await self._reply(event, W.BACKUP_UNREACHABLE)
            return
        except RPCError:
            await self._reply(event, W.CANT_COPY)
            return
        chat_peer = await event.get_input_chat()
        banner = await store.upsert_banner(
            self.db,
            self.user_id,
            event.chat_id,
            getattr(chat_peer, "access_hash", None),
            getattr(chat, "title", None),
            backup.channel_id,
            backup.access_hash,
            copy.id,
        )
        await self._reply(event, W.BANNER_SAVED)
        await self._refresh_info(banner.id)

    async def _cmd_interval(self, event, seconds: int) -> None:
        chat = await event.get_chat()
        if not self._is_group(chat):
            await self._reply(event, W.ONLY_GROUPS)
            return
        banner = await store.get_banner(self.db, self.user_id, event.chat_id)
        if banner is None:
            await self._reply(event, W.NEED_BANNER)
            return
        if seconds < MIN_BANNER_INTERVAL:
            await self._reply(event, W.TOO_FAST)
            return
        if seconds > MAX_BANNER_INTERVAL:
            await self._reply(event, W.TOO_SLOW)
            return
        next_run = utcnow() + timedelta(seconds=seconds) if banner.enabled else None
        await store.set_interval(self.db, banner.id, seconds, next_run)
        if banner.enabled:
            self.schedule(banner.id)  # از همین لحظه با بازه‌ی جدید
        await self._reply(event, W.interval_set(seconds))
        await self._refresh_info(banner.id)

    async def _cmd_toggle(self, event, on: bool) -> None:
        chat = await event.get_chat()
        if not self._is_group(chat):
            await self._reply(event, W.ONLY_GROUPS)
            return
        banner = await store.get_banner(self.db, self.user_id, event.chat_id)
        if banner is None:
            await self._reply(event, W.NEED_BANNER)
            return
        if on:
            if not banner.interval_seconds:
                await self._reply(event, W.NEED_INTERVAL)
                return
            if not banner.enabled and await store.count_enabled(self.db, self.user_id) >= MAX_ACTIVE_BANNERS:
                await self._reply(event, W.TOO_MANY_ACTIVE)
                return
            await store.set_enabled(self.db, banner.id, True, utcnow() + timedelta(seconds=banner.interval_seconds))
            self.schedule(banner.id)
            await self._reply(event, W.TABCHI_ON)
        else:
            await store.set_enabled(self.db, banner.id, False)
            self.unschedule(banner.id)
            await self._reply(event, W.TABCHI_OFF)
        await self._refresh_info(banner.id)

    async def _cmd_delete(self, event) -> None:
        banner = await store.get_banner(self.db, self.user_id, event.chat_id)
        if banner is None:
            await self._reply(event, W.NEED_BANNER)
            return
        self.unschedule(banner.id)
        await store.delete_banner(self.db, banner.id)
        peer = make_input_peer(banner.backup_channel_id, banner.backup_access_hash)
        ids = [i for i in (banner.backup_msg_id, banner.info_msg_id) if i]
        try:
            await self.client.delete_messages(peer, ids)
        except Exception:
            pass
        await self._reply(event, W.BANNER_DELETED)

    async def _refresh_info(self, banner_id: int) -> None:
        """پیام خلاصه‌ی تنظیمات داخل کانال پشتیبان (اسم گروه، آیدی، بازه، وضعیت)."""
        try:
            b = await store.get_banner_by_id(self.db, banner_id)
            if b is None:
                return
            interval = format_interval(b.interval_seconds) if b.interval_seconds else "تنظیم نشده"
            text = (
                f"📌 بنر گروه: {b.chat_title or '—'}\n"
                f"🆔 آیدی گروه: {b.chat_id}\n"
                f"⏱ بازه: هر {interval}\n"
                f"🔘 تبچی: {'روشن' if b.enabled else 'خاموش'}"
            )
            peer = make_input_peer(b.backup_channel_id, b.backup_access_hash)
            if b.info_msg_id:
                try:
                    await self.client.edit_message(peer, b.info_msg_id, text, parse_mode=None)
                    return
                except MessageNotModifiedError:
                    return
                except RPCError:
                    pass
            m = await self.client.send_message(peer, text, parse_mode=None)
            await store.set_info_msg(self.db, b.id, m.id)
        except Exception:
            log.info("info refresh failed (user %s)", self.user_id)

    # ------------------------------------------------------------ زمان‌بندی
    def schedule(self, banner_id: int) -> None:
        self.unschedule(banner_id)
        self._tasks[banner_id] = asyncio.create_task(self._banner_loop(banner_id))

    def unschedule(self, banner_id: int) -> None:
        t = self._tasks.pop(banner_id, None)
        if t is not None:
            t.cancel()

    async def _banner_loop(self, banner_id: int) -> None:
        """زمان‌بندی بدون «لغزش»: موعد بعدی همیشه از موعد قبلی حساب می‌شه، نه از لحظه‌ی ارسال.
        اگه عقب افتادیم (قطعی یا فلود)، یک‌جا جبران نمی‌کنیم تا حساب اسپم نشه."""
        while True:
            try:
                b = await store.get_banner_by_id(self.db, banner_id)
                if b is None or not b.enabled or not b.interval_seconds:
                    return
                interval = timedelta(seconds=b.interval_seconds)
                due = b.next_run_at or (utcnow() + interval)
                while True:
                    remaining = (due - utcnow()).total_seconds()
                    if remaining <= 0:
                        break
                    await asyncio.sleep(min(remaining, 15))

                outcome, extra = await self._send_banner(b)
                now = utcnow()
                if outcome == "ok":
                    nxt = due + interval
                    if nxt <= now:
                        nxt = now + interval
                    await store.mark_sent(self.db, b.id, now, nxt)
                elif outcome == "wait":
                    await store.set_next_run(self.db, b.id, now + timedelta(seconds=max(1, int(extra)) + 1))
                elif outcome == "fatal":
                    await store.set_enabled(self.db, b.id, False)
                    await self._refresh_info(b.id)
                    return
                elif outcome == "dead":
                    return
                else:  # fail
                    streak = await store.bump_fail(self.db, b.id, now + interval)
                    if streak >= FAIL_STREAK_LIMIT:
                        await store.set_enabled(self.db, b.id, False)
                        await self.sup.notify(self.user_id, W.notify_failures(b.chat_title), key=f"fail:{b.id}")
                        await self._refresh_info(b.id)
                        return
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("banner loop error (banner %s)", banner_id)
                await asyncio.sleep(10)

    async def _banner_message(self, b, force: bool = False):
        key = (b.backup_channel_id, b.backup_msg_id)
        cached = self._cache.get(key)
        if cached and not force and time.monotonic() - cached[1] < 1200:
            return cached[0]
        peer = make_input_peer(b.backup_channel_id, b.backup_access_hash)
        msg = await self.client.get_messages(peer, ids=b.backup_msg_id)
        if msg is None:
            return None
        self._cache[key] = (msg, time.monotonic())
        return msg

    async def _send_banner(self, b) -> tuple[str, float]:
        """خروجی: (ok | wait | fail | fatal | dead, ثانیه‌ی انتظار)."""
        async with self._send_lock:
            now_m = time.monotonic()
            if now_m < self._paused_until:
                return "wait", self._paused_until - now_m
            gap = self._last_send + ACCOUNT_MIN_GAP_SECONDS - now_m
            if gap > 0:
                await asyncio.sleep(gap)
            try:
                msg = await self._banner_message(b)
                if msg is None:
                    await self.sup.notify(self.user_id, W.notify_failures(b.chat_title), key=f"gone:{b.id}")
                    return "fatal", 0
                target = make_input_peer(b.chat_id, b.chat_access_hash)
                try:
                    await self.client.send_message(target, msg)
                except FileReferenceExpiredError:
                    msg = await self._banner_message(b, force=True)
                    await self.client.send_message(target, msg)
                self._last_send = time.monotonic()
                return "ok", 0
            except FloodWaitError as e:
                self._paused_until = time.monotonic() + e.seconds
                await self.sup.notify(self.user_id, W.notify_flood(e.seconds), key="flood", cooldown=1800)
                return "wait", float(e.seconds)
            except SlowModeWaitError as e:
                await self.sup.notify(
                    self.user_id, W.notify_slowmode(b.chat_title, e.seconds), key=f"slow:{b.id}", cooldown=21600
                )
                return "wait", float(e.seconds)
            except _FORBIDDEN_ERRORS:
                await self.sup.notify(self.user_id, W.notify_forbidden(b.chat_title), key=f"forb:{b.id}")
                return "fatal", 0
            except _DEAD_ERRORS as e:
                await self._handle_dead(e)
                return "dead", 0
            except (RPCError, ConnectionError, asyncio.TimeoutError, OSError) as e:
                log.warning("send failed (banner %s): %s", b.id, type(e).__name__)
                return "fail", 0
