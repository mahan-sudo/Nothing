from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from . import texts as T
from .config import Settings
from .services.payments import expire_due_payments
from .utils import utcnow

log = logging.getLogger(__name__)


async def expiry_loop(bot: Bot, db, settings: Settings) -> None:
    """هر ۲۰ ثانیه پرداخت‌های منقضی‌شده رو می‌بنده و پیامشون رو ویرایش می‌کنه.
    اگه چند نسخه از ربات اجرا بشه، SKIP LOCKED باعث می‌شه هر پرداخت فقط یک‌بار پردازش بشه."""
    while True:
        try:
            async with db.begin() as session:
                expired = await expire_due_payments(session, utcnow())
            for item in expired:
                if not (item.chat_id and item.message_id):
                    continue
                if item.was == "pending":
                    text = T.payment_details(item.payment, settings.card_number, settings.card_holder, expired=True)
                else:
                    text = T.RECEIPT_EXPIRED
                try:
                    await bot.edit_message_text(text, chat_id=item.chat_id, message_id=item.message_id, reply_markup=None)
                except TelegramAPIError:
                    log.info("could not edit expired payment message %s", item.payment.id)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("expiry loop error")
        await asyncio.sleep(20)
